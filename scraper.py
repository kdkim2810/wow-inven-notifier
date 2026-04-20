import os
import requests
from bs4 import BeautifulSoup
import json

# GitHub Secrets에서 가져올 웹훅 URL
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
BOARD_URL = "https://www.inven.co.kr/board/wow/2972"
LAST_ID_FILE = "last_id.txt"

def get_last_id():
    if os.path.exists(LAST_ID_FILE):
        with open(LAST_ID_FILE, "r") as f:
            return int(f.read().strip())
    return 0

def save_last_id(post_id):
    with open(LAST_ID_FILE, "w") as f:
        f.write(str(post_id))

def send_discord_msg(title, link):
    data = {
        "content": f"🚨 **새로운 파티글이 올라왔습니다!**\n[{title}]({link})"
    }
    requests.post(WEBHOOK_URL, json=data)

def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    response = requests.get(BOARD_URL, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 인벤 게시판의 공지를 제외한 일반 글 목록 가져오기
    rows = soup.select('.board-list tbody tr:not(.notice)')
    
    last_id = get_last_id()
    new_last_id = last_id
    new_posts = []

    # 최신 글부터 확인 (위에서부터 아래로)
    for row in rows:
        title_tag = row.select_one('.subject-link')
        if not title_tag:
            continue
            
        title = title_tag.text.strip()
        link = title_tag['href']
        
        # URL에서 글 번호(l=숫자) 추출
        try:
            post_id = int(link.split('l=')[1].split('&')[0])
        except IndexError:
            continue

        if post_id > last_id:
            new_posts.append({"id": post_id, "title": title, "link": link})
            if post_id > new_last_id:
                new_last_id = post_id

    # 오래된 글부터 디스코드로 전송 (역순)
    for post in reversed(new_posts):
        # 처음 실행해서 last_id가 0일 때는 도배 방지를 위해 최신 글 1개만 전송
        if last_id == 0:
            send_discord_msg(post['title'], post['link'])
            break
        else:
            send_discord_msg(post['title'], post['link'])

    # 가장 높은 글 번호를 갱신
    if new_last_id > last_id:
        save_last_id(new_last_id)

if __name__ == "__main__":
    main()
