import argparse
import math
import os
import random
import re
import smtplib
import time
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK')
GMAIL_USER = os.environ.get('GMAIL_USER')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD')
BOARD_URL = 'https://www.inven.co.kr/board/wow/2972'
LAST_ID_FILE = 'last_id.txt'
FAIL_COUNT_FILE = 'fail_count.txt'
FAIL_THRESHOLD = 3
MAX_PAGES = 20
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'}


def read_counter(path):
    try:
        value = int(Path(path).read_text(encoding='utf-8').strip())
    except FileNotFoundError:
        if path == LAST_ID_FILE:
            raise RuntimeError('마지막 처리 ID 파일 없음: 알림 누락 방지를 위해 실행 중단') from None
        return 0
    except (ValueError, OSError):
        raise RuntimeError(f'{path}: 상태 파일 읽기 실패. 원본 보존') from None
    if value < 0:
        raise ValueError(f'{path}: 음수 상태 값')
    return value


def write_counter(path, value):
    temporary = Path(str(path) + '.tmp')
    temporary.write_text(str(value), encoding='utf-8')
    temporary.replace(path)


def fetch_with_retry(url, retries=4, delay=15):
    if retries < 1:
        raise ValueError('인벤 요청 횟수는 1 이상이어야 합니다')
    last_reason = '원인 미확인'
    for attempt in range(1, retries + 1):
        print(f'인벤 요청 시작 [{attempt}/{retries}]', flush=True)
        try:
            response = requests.get(url, headers=HEADERS, timeout=(15, 30))
            response.raise_for_status()
            print(f'인벤 응답: HTTP {response.status_code}, {len(response.content)} bytes', flush=True)
            return response
        except requests.RequestException as exc:
            # URL/응답 본문을 노출하지 않고 오류 종류와 상태 코드만 기록한다.
            status = exc.response.status_code if exc.response is not None else None
            last_reason = f'HTTP {status}' if status is not None else type(exc).__name__
            print(f'인벤 요청 실패 [{attempt}/{retries}]: {last_reason}', flush=True)
            transient = isinstance(exc, (requests.Timeout, requests.ConnectionError))
            if isinstance(exc, requests.exceptions.SSLError):
                transient = False
            if status is not None:
                transient = status in (408, 429) or 500 <= status < 600
            if not transient:
                raise RuntimeError(f'인벤 요청 중단: {last_reason} (재시도 대상 아님)') from None
            if attempt < retries:
                wait = min(delay * 2 ** (attempt - 1), 60) + random.uniform(0, 3)
                if status == 429:
                    try:
                        retry_after = float(exc.response.headers.get('Retry-After', wait))
                    except (ValueError, TypeError):
                        retry_after = wait
                    if math.isfinite(retry_after):
                        if retry_after > 60:
                            raise RuntimeError('인벤 요청 제한: 다음 정기 실행에서 재시도') from None
                        wait = max(wait, retry_after)
                print(f'{wait:.1f}초 후 인벤 재접속', flush=True)
                time.sleep(wait)
    raise RuntimeError(f'인벤 접속 실패: {retries}회 재시도 소진, 최종 원인 {last_reason}')


def parse_posts(html):
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.select('.board-list tbody tr:not(.notice)')
    posts = {}
    for row in rows:
        number = row.select_one('.num')
        if number and not number.get_text(strip=True).replace(',', '').isdigit():
            continue  # 공지/광고는 최신 글 번호에 포함하지 않는다.
        tag = row.select_one('.subject-link') or row.select_one('.sj_line') or row.select_one('.tit a')
        if not tag:
            continue
        link = urljoin(BOARD_URL, tag.get('href', ''))
        parsed = urlparse(link)
        if parsed.hostname != 'www.inven.co.kr':
            continue
        match = re.fullmatch(r'/board/wow/2972/(\d+)/?', parsed.path)
        if match:
            post_id = int(match.group(1))
        elif parsed.path.rstrip('/') == '/board/wow/2972':
            candidate = parse_qs(parsed.query).get('l', [''])[0]
            if not candidate.isdigit():
                continue
            post_id = int(candidate)
        else:
            continue
        title = ' '.join(tag.get_text(' ', strip=True).split())
        if post_id > 0 and title:
            posts[post_id] = {'id': post_id, 'title': title, 'link': link}
    if not posts:
        raise RuntimeError('게시글 파싱 실패: 빈 목록/점검/차단 또는 게시판 구조 변경')
    return sorted(posts.values(), key=lambda post: post['id'])


def collect_new_posts(last_id):
    posts = {}
    previous_min = None
    for page in range(1, MAX_PAGES + 1):
        url = BOARD_URL if page == 1 else f'{BOARD_URL}?page={page}'
        batch = parse_posts(fetch_with_retry(url).text)
        print(f'목록 {page}쪽: {len(batch)}개, ID {batch[0]["id"]}~{batch[-1]["id"]}')
        posts.update((post['id'], post) for post in batch if post['id'] > last_id)
        if last_id == 0 or batch[0]['id'] <= last_id:
            result = sorted(posts.values(), key=lambda post: post['id'])
            return result[-1:] if last_id == 0 else result
        if previous_min is not None and batch[0]['id'] >= previous_min:
            raise RuntimeError('목록 페이지 반복: 누락 방지를 위해 상태를 유지합니다')
        previous_min = batch[0]['id']
    raise RuntimeError(f'{MAX_PAGES}쪽 이내에 이전 처리 지점에 도달하지 못했습니다. 상태 유지')


def send_discord_msg(title, link):
    if not WEBHOOK_URL:
        raise RuntimeError('DISCORD_WEBHOOK 설정 누락')
    data = {'content': f'🚨 **새로운 파티글이 올라왔습니다!**\n[{title[:1500]}]({link})',
            'allowed_mentions': {'parse': []}}
    for attempt in range(3):
        try:
            response = requests.post(WEBHOOK_URL, json=data, timeout=(10, 30), allow_redirects=False)
        except requests.RequestException as exc:
            # 웹훅 URL/토큰을 로그에 노출하지 않는다.
            raise RuntimeError(f'디스코드 접속 실패: {type(exc).__name__}') from None
        if 200 <= response.status_code < 300:
            print(f'디스코드 전송 성공: {title}')
            return
        if response.status_code == 429 and attempt < 2:
            try:
                wait = float(response.json().get('retry_after', 5))
                if not math.isfinite(wait):
                    wait = 5
            except (ValueError, TypeError, AttributeError):
                wait = 5
            if wait > 60:
                raise RuntimeError(f'디스코드 요청 제한: {wait:g}초, 다음 실행에서 재시도')
            time.sleep(max(wait, 1))
            continue
        raise RuntimeError(f'디스코드 전송 실패: HTTP {response.status_code}')


def send_fail_email(fail_count, reason):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print('Gmail 설정 누락: 실패 메일을 보내지 못했습니다')
        return
    try:
        msg = MIMEText(f'wow-inven-notifier가 연속 {fail_count}회 실패했습니다.\n원인: {reason}\n'
                       '복구 전까지 같은 장애 메일은 반복 발송하지 않습니다.\n'
                       'https://github.com/kdkim2810/wow-inven-notifier/actions')
        msg['Subject'] = f'[WoW 인벤 알리미] 연속 {fail_count}회 실패 알림'
        msg['From'] = GMAIL_USER
        msg['To'] = GMAIL_USER
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
        print('실패 알림 메일 전송 완료')
    except Exception as exc:
        print(f'실패 메일 전송 오류: {type(exc).__name__}')


def main(dry_run=False):
    try:
        last_id = read_counter(LAST_ID_FILE)
        new_posts = collect_new_posts(last_id)
        print(f'마지막 처리 ID: {last_id}, 새 글: {len(new_posts)}개, dry_run={dry_run}')
        if dry_run:
            print('접속/파싱 점검 완료. 알림 및 상태 저장 생략')
            return 0
        if not WEBHOOK_URL:
            raise RuntimeError('DISCORD_WEBHOOK 설정 누락')
        for post in new_posts:
            send_discord_msg(post['title'], post['link'])
            # 성공한 글만 즉시 기록. 다음 글 실패 시 다음 실행에서 재시도한다.
            write_counter(LAST_ID_FILE, post['id'])
        write_counter(FAIL_COUNT_FILE, 0)
        return 0
    except Exception as exc:
        reason = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else type(exc).__name__
        print(f'실행 실패: {reason}')
        if not dry_run:
            try:
                fail_count = read_counter(FAIL_COUNT_FILE) + 1
                write_counter(FAIL_COUNT_FILE, fail_count)
                if fail_count == FAIL_THRESHOLD:
                    send_fail_email(fail_count, reason)
            except (OSError, ValueError, RuntimeError):
                print('실패 횟수 저장 불가: 기존 상태 파일을 보존합니다')
        return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='접속/파싱만 점검, 알림/상태 변경 없음')
    raise SystemExit(main(dry_run=parser.parse_args().dry_run))
