import os
import requests
from bs4 import BeautifulSoup
import json

# GitHub Secrets에서 가져올 웹훅 URL
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
BOARD_URL = "https://www.inven.co.kr/board/wow/2972"
STATE_FILE = "state.json"

# 🚫 여기에 보기 싫은 단어들을 적어주세요! (따옴표와 쉼표 주의)
BLOCKED_WORDS = ["버스", "쐐기", "초보", "다이소", "갠룻", "주사위", "학원", "렙업", "저득", "레벨", "대장정"]

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_id": 0}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def send_discord_msg(title, link):
    if not WEBHOOK_URL:
        print("에러: DISCORD_WEBHOOK URL이 비어있습니다.")
        return
        
    # 💡 "새로운 파티글..." 문구를 제거하고 제목과 링크만 보냅니다. (미리보기 유지)
    data = {
        "content": f"[{title}]({link})"
    }
    response = requests.post(WEBHOOK_URL, json=data)
    if response.status_code == 204:
        print(f"디스코드 전송 성공: {title}")
    else:
        print(f"디스코드 전송 실패: {response.status_code}")

def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    response = requests.get(BOARD_URL, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    rows = soup.select('.board-list tbody tr:not(.notice)')
    
    state = load_state()
    last_id = state["last_id"]
    new_last_id = last_id
    new_posts = []

    for row in rows:
        title_tag = row.select_one('.subject-link') or row.select_one('.sj_line') or row.select_one('.tit a')
        if not title_tag:
            continue
            
        title = " ".join(title_tag.text.split())
        
        # 🛑 필터링 핵심: 제목에 차단할 단어가 하나라도 있으면 무시하고 넘어감
        if any(word in title for word in BLOCKED_WORDS):
            continue

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

    if last_id == 0 and new_posts:
        newest_post = new_posts[0]
        send_discord_msg(newest_post['title'], newest_post['link'])
        print("-> 최초 실행이므로 가장 최신 글 1개만 전송했습니다.")
    else:
        for post in reversed(new_posts):
            send_discord_msg(post['title'], post['link'])

    if new_last_id > last_id:
        state["last_id"] = new_last_id
        save_state(state)
        print(f"-> 마지막 글 번호 갱신 완료: {new_last_id}")

if __name__ == "__main__":
    main()
