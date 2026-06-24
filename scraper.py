import os
import time
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# GitHub Secrets에서 가져올 웹훅 URL
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
BOARD_URL = "https://www.inven.co.kr/board/wow/2972"
LAST_ID_FILE = "last_id.txt"


def fetch_with_retry(url, retries=3, delay=10):
    for attempt in range(1, retries + 1):
        try:
            ua = UserAgent()
            headers = {"User-Agent": ua.random}
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            print(f"[{attempt}/{retries}] 요청 실패: {e}")
            if attempt < retries:
                print(f"-> {delay}초 후 재시도...")
                time.sleep(delay)
    raise Exception(f"최대 재시도 횟수({retries}) 초과. 스크래핑 실패.")


def get_last_id():
    if os.path.exists(LAST_ID_FILE):
        with open(LAST_ID_FILE, "r") as f:
            return int(f.read().strip())
    return 0


def save_last_id(post_id):
    with open(LAST_ID_FILE, "w") as f:
        f.write(str(post_id))


def send_discord_msg(title, link):
    if not WEBHOOK_URL:
        print("에러: DISCORD_WEBHOOK URL이 비어있습니다. Secrets 설정을 확인하세요.")
        return

    data = {
        "content": f"🚨 **새로운 파티글이 올라왔습니다!**\n[{title}]({link})"
    }

    response = requests.post(WEBHOOK_URL, json=data)
    if response.status_code == 204:
        print(f"디스코드 전송 성공: {title}")
    else:
        print(f"디스코드 전송 실패: 상태 코드 {response.status_code}")


def main():
    response = fetch_with_retry(BOARD_URL)
    soup = BeautifulSoup(response.text, 'html.parser')

    # 인벤 게시판의 공지를 제외한 일반 글 목록 가져오기
    rows = soup.select('.board-list tbody tr:not(.notice)')

    last_id = get_last_id()
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


if __name__ == "__main__":
    main()
