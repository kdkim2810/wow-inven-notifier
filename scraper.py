import os
import time
import smtplib
import requests
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# GitHub Secrets에서 가져올 값들
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

BOARD_URL = "https://www.inven.co.kr/board/wow/2972"
LAST_ID_FILE = "last_id.txt"
FAIL_COUNT_FILE = "fail_count.txt"
FAIL_THRESHOLD = 3


def fetch_with_retry(url, retries=3, delay=10):
    ua = UserAgent()
    for attempt in range(1, retries + 1):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"}
            print(f"[{attempt}/{retries}] 요청 시도 중... User-Agent: {headers['User-Agent']}")
            response = requests.get(url, headers=headers, timeout=15)
            print(f"[{attempt}/{retries}] 응답 상태 코드: {response.status_code}")
            print(f"[{attempt}/{retries}] 응답 HTML 길이: {len(response.text)}")
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            print(f"[{attempt}/{retries}] 요청 실패: {e}")
            if attempt < retries:
                print(f"-> {delay}초 후 재시도...")
                time.sleep(delay)
    return None


def get_fail_count():
    if os.path.exists(FAIL_COUNT_FILE):
        with open(FAIL_COUNT_FILE, "r") as f:
            return int(f.read().strip())
    return 0


def save_fail_count(count):
    with open(FAIL_COUNT_FILE, "w") as f:
        f.write(str(count))


def get_last_id():
    if os.path.exists(LAST_ID_FILE):
        with open(LAST_ID_FILE, "r") as f:
            content = f.read().strip()
            print(f"-> last_id.txt 파일 내용: '{content}'")
            return int(content)
    print("-> last_id.txt 파일 없음. last_id = 0 으로 시작")
    return 0


def save_last_id(post_id):
    with open(LAST_ID_FILE, "w") as f:
        f.write(str(post_id))


def send_discord_msg(title, link):
    if not WEBHOOK_URL:
        print("에러: DISCORD_WEBHOOK URL이 비어있습니다.")
        return
    data = {"content": f"🚨 **새로운 파티글이 올라왔습니다!**\n[{title}]({link})"}
    response = requests.post(WEBHOOK_URL, json=data)
    if response.status_code == 204:
        print(f"디스코드 전송 성공: {title}")
    else:
        print(f"디스코드 전송 실패: 상태 코드 {response.status_code}")


def send_fail_email(fail_count):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("에러: Gmail 설정이 비어있습니다. Secrets를 확인하세요.")
        return
    try:
        msg = MIMEText(
            f"wow-inven-notifier가 연속 {fail_count}회 스크래핑에 실패했습니다.\n\n"
            f"인벤 서버 차단 또는 네트워크 문제일 수 있습니다.\n"
            f"GitHub Actions 로그를 확인해주세요.\n\n"
            f"https://github.com/kdkim2810/wow-inven-notifier/actions"
        )
        msg['Subject'] = f"[WoW 인벤 알리미] 연속 {fail_count}회 실패 알림"
        msg['From'] = GMAIL_USER
        msg['To'] = GMAIL_USER

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
        print(f"실패 알림 메일 전송 완료 ({fail_count}회 연속 실패)")
    except Exception as e:
        print(f"메일 전송 실패: {e}")


def main():
    print("=" * 50)
    print(f"-> 현재 작업 디렉토리: {os.getcwd()}")
    print(f"-> last_id.txt 존재 여부: {os.path.exists(LAST_ID_FILE)}")
    print(f"-> fail_count.txt 존재 여부: {os.path.exists(FAIL_COUNT_FILE)}")

    response = fetch_with_retry(BOARD_URL)

    # 스크래핑 실패 처리
    if response is None:
        fail_count = get_fail_count() + 1
        save_fail_count(fail_count)
        print(f"-> 스크래핑 실패. 누적 실패 횟수: {fail_count}")
        if fail_count >= FAIL_THRESHOLD:
            send_fail_email(fail_count)
        return

    # 스크래핑 성공 시 실패 카운트 리셋
    save_fail_count(0)

    soup = BeautifulSoup(response.text, 'html.parser')
    rows = soup.select('.board-list tbody tr:not(.notice)')
    print(f"-> 파싱된 행 수: {len(rows)}")

    last_id = get_last_id()
    print(f"-> 현재 last_id: {last_id}")

    new_last_id = last_id
    new_posts = []

    for row in rows:
        title_tag = row.select_one('.subject-link') or row.select_one('.sj_line') or row.select_one('.tit a')
        if not title_tag:
            continue

        title = " ".join(title_tag.text.split())
        link = title_tag.get('href', '')

        try:
            if 'l=' in link:
                post_id = int(link.split('l=')[1].split('&')[0])
            else:
                post_id = int(link.split('?')[0].rstrip('/').split('/')[-1])
        except (IndexError, ValueError):
            continue

        if post_id > last_id:
            new_posts.append({"id": post_id, "title": title, "link": link})
        if post_id > new_last_id:
            new_last_id = post_id

    print(f"-> 새로 발견된 글 개수: {len(new_posts)}개")
    if rows:
        print(f"-> 게시판 최신 글 ID: {new_last_id}")

    # 최초 실행과 평상시 전송 로직 분리
    if last_id == 0 and new_posts:
        newest_post = new_posts[0]
        send_discord_msg(newest_post['title'], newest_post['link'])
        print("-> 최초 실행이므로 가장 최신 글 1개만 전송했습니다.")
    else:
        for post in reversed(new_posts):
            send_discord_msg(post['title'], post['link'])

    if new_last_id > last_id:
        save_last_id(new_last_id)
        print(f"-> 마지막 글 번호 갱신 완료: {new_last_id}")

    print("=" * 50)


if __name__ == "__main__":
    main()
