# AltBrief — 자동 뉴스 수집 복구판

GitHub Actions가 **3시간마다 공개 Google News RSS**에서 대체투자 뉴스를 수집하고 `news.json`을 갱신한 다음 **GitHub Pages**에 배포합니다. API 키가 필요하지 않습니다. 개인 즐겨찾기는 기기 내 저장(localStorage) 방식이며 팀 공유 저장함은 없습니다.

## 설치 / 기존 GitHub 저장소 교체

1. 이 압축파일을 해제한 뒤 **안에 있는 파일과 `.github` 폴더**를 `altbrief-new` 저장소의 **루트**에 업로드하세요. ZIP 파일 자체를 업로드하지 마세요. `.github/workflows/update-news.yml` 경로가 꼭 유지되어야 합니다.
2. 이전에 별도로 설치한 `update-news*.yml` 등 **중복 뉴스 수집 워크플로를 제거**하세요. `main` 브랜치가 기본 브랜치인지 확인하세요. 다른 브랜치를 쓰면 workflow의 `branches: [main]`을 변경하세요.
3. GitHub 저장소 → **Settings → Actions → General** 에서 workflow 권한을 **Read and write permissions**로 설정하세요. 조직 정책이 우선할 수 있습니다.
4. **Settings → Pages → Build and deployment → Source = GitHub Actions**로 설정하세요.
5. **Actions → AltBrief - Refresh News and Deploy → Run workflow** 를 눌러 최초 1회 실행합니다. 실행 후 `Collect latest news`, `Print freshness diagnostics`, `Commit latest dataset`, `Deploy Pages` 단계가 성공했는지 확인하세요.
6. `news.json`의 `updated_at`, `feed_successes`, `feed_failures`, `article_count`가 변했는지 확인한 뒤 GitHub Pages URL을 열어보세요. 화면 내 **마지막 업데이트 (KST)**가 새로 바뀌어야 합니다.

## 자동 수집이 다시 멈출 때

- **Actions 메뉴에 워크플로가 아예 없음:** `.github/workflows/update-news.yml` 위치와 기본 브랜치 확인.
- **Collect latest news 실패:** Actions 상세 로그를 보고 RSS 접속 오류 / 의존성 설치 오류 확인.
- **Commit latest dataset 실패 (403):** 워크플로 `contents: write`와 저장소 Actions의 쓰기 권한, 브랜치 보호 규칙 확인.
- **Deploy Pages 실패:** Pages의 Source가 GitHub Actions인지, Pages 활성화 권한이 있는지 확인.
- **Actions는 성공인데 사이트가 이전 데이터:** 브라우저 강력 새로고침, Pages URL의 `/news.json` 내용 확인. 이 버전은 `news.json`을 서비스워커에 캐시하지 않습니다.
- **일정이 실행되지 않음:** GitHub Actions `schedule`은 정시 정확한 실행을 보장하지 않고 지연/누락될 수 있습니다. 공개 저장소는 장기간 활동이 없으면 scheduled workflow가 자동 비활성화될 수 있습니다. Actions에서 재활성화하세요. 기본 브랜치에 workflow가 있어야 합니다.
- **일부 소스 실패:** `status: partial`로 표시하고 다른 소스의 데이터는 보존합니다. 전부 실패하면 기존 `news.json`을 덮어쓰지 않고 workflow가 실패합니다.

## 수동 테스트

```bash
python -m pip install -r requirements.txt
python update_news.py
python -m http.server 8000
```

`http://localhost:8000`에서 확인합니다. 뉴스 수집 검색어와 자산군은 `sources.json`에서 수정하세요. RSS의 검색 결과는 수시로 달라질 수 있습니다.

## 데이터 / 요약 정책

- 데이터는 공개 RSS의 제목, 발행시각, 출처, 링크, 설명만 사용합니다. **기사 원문 자동 추출 또는 생성형 AI 요약은 포함하지 않습니다.** 과거 프로젝트의 2~4문장 AI 요약 기능과는 차이가 있으며, 현재 보여주는 설명은 사실관계가 확인되지 않은 공개 RSS 텍스트입니다.
- 기사 원문으로 직접 연결합니다. 기사 전문 재배포를 하지 않습니다.
- 페이지 공개 배포 전에 소스 서비스 이용약관과 사내 정보보안 정책을 확인하세요.
- `MAX_AGE_DAYS=21`, `MAX_ARTICLES=500` 등 환경변수로 범위를 조정할 수 있습니다.
