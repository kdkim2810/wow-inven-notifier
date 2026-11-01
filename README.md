# wow-inven-notifier

와우 인벤 파티찾기 게시판(2972)의 새 글을 Discord로 알립니다.
외부 cron-job.org가 `scraper.yml`의 `workflow_dispatch`를 호출합니다.
기존 15분 실행 주기는 외부 서비스에서 관리하며, GitHub schedule은 사용하지 않습니다.

## 실행 및 점검

- Python 3.12, `python -m pip install requests beautifulsoup4`
- `python scraper.py`: 정상 운영 (기존 GitHub Secrets 사용)
- `python scraper.py --dry-run`: 실제 인벤 접속/파싱만 확인. 알림 전송과 상태 변경 없음
- `python -m unittest -v`: 외부 전송 없이 회귀 테스트
- 코드 push 시 테스트와 dry-run을 자동 실행합니다. 정기 실행과 동일한 concurrency 그룹을 사용합니다.

## 상태와 장애 처리

- `last_id.txt`: Discord 전송이 확인된 마지막 게시글 ID. 전송 실패 시 해당 글 이후는 다음 실행에서 재시도합니다.
- `fail_count.txt`: 접속, 파싱 또는 전송의 연속 실패 횟수. 전체 실행 성공 후 0으로 초기화합니다.
- `state.json`: 과거 형식으로, 현재 코드에서 사용하지 않습니다.
- 빈 목록/점검 페이지를 성공으로 처리하지 않으며 실패 상태를 GitHub Actions에도 표시합니다.
- 실패한 실행에서도 상태 파일을 저장합니다. 연속 3회 실패 시 기존 Gmail 설정으로 1회 알립니다. 복구 후 다시 3회 실패하면 새로 알립니다.
- 장애 후 새 글이 첫 페이지를 넘으면 최대 20페이지까지 확인합니다. 이전 처리 지점을 찾지 못하면 상태를 유지하고 실패로 표시합니다.
- Discord 429 응답은 대기 후 재시도합니다. 네트워크 응답 유실 또는 상태 push 실패 시 중복 알림 가능성은 있습니다.
