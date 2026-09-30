# 협업 컨벤션 가이드 (Convention Guide)

본 문서는 프로젝트 개발 시 일관성 있는 협업과 관리를 위한 Git 브랜치, 이슈, 커밋, Pull Request(PR) 작성 규칙을 정의합니다.

---

## 1. 브랜치 전략 및 네이밍 (Branch Convention)

기본 브랜치는 `main`과 `dev`를 기준으로 하며, 기능 개발은 `dev`에서 분기한 작업 브랜치에서 진행합니다.

### 브랜치 종류
- `main`: 상용 배포 가능한 안정화 브랜치
- `dev`: 개발 통합 브랜치 (모든 PR의 기본 병합 대상)
- `feature/<이슈번호>-<작업명>`: 새로운 기능 개발
- `fix/<이슈번호>-<버그명>`: 버그 수정
- `refactor/<이슈번호>-<작업명>`: 리팩토링
- `chore/<이슈번호>-<작업명>`: 환경 설정 및 의존성 관리

### 브랜치 이름 예시
```text
feature/5-user-onboarding
feature/9-websocket-map-sync
fix/12-settlement-calculation-error
refactor/3-redis-geo-module
chore/1-alembic-setup
```

---

## 2. 이슈 제목 컨벤션 (Issue Title Convention)

이슈 제목은 대괄호 안에 태그(`[Tag]`)를 명시하고, 어떤 작업을 진행할 것인지 간결한 명사형/개조식 문장으로 작성합니다.

### 형식
```text
[Tag] 작업 요약
```

### Tag 종류
| Tag | 설명 | 예시 |
| :--- | :--- | :--- |
| `[Feat]` | 새로운 기능 또는 API 개발 | `[Feat] 기기 등록 및 온보딩 API 구현` |
| `[Fix]` | 버그 또는 오류 수정 | `[Fix] 소켓 재연결 시 위치 데이터 누락 수정` |
| `[Refactor]` | 코드 구조 개선, 성능 최적화 | `[Refactor] WebSocket 매니저 연결 로직 분리` |
| `[Chore]` | 의존성 추가, 빌드/환경 설정, DB 마이그레이션 | `[Chore] Alembic 비동기 마이그레이션 환경 구축` |
| `[Docs]` | 문서 작성 및 수정 | `[Docs] 데이터베이스 스키마 및 컨벤션 문서 추가` |
| `[Test]` | 테스트 코드 작성 및 검증 | `[Test] 온보딩 API 닉네임 길이 검증 단위 테스트` |

---

## 3. 커밋 메시지 컨벤션 (Commit Convention)

커밋 메시지는 Conventional Commits 표준을 따르며, 영어 소문자 태그를 사용합니다.

### 형식
```text
<type>: <subject>

[선택적 본문(body)]
```

### Type 종류
| Type | 설명 |
| :--- | :--- |
| `feat` | 새로운 기능 추가 |
| `fix` | 버그 수정 |
| `refactor` | 기능 변경 없는 코드 구조 개선/리팩토링 |
| `chore` | 패키지 의존성, 빌드 설정, .gitignore 등 기타 수정 |
| `docs` | 문서 추가 및 수정 (README, 주석 등) |
| `test` | 테스트 코드 추가, 테스트 리팩토링 |
| `style` | 코드 포맷팅, 세미콜론 누락 등 (코드 동작 변경 없음) |

### 작성 규칙
1. `type` 뒤에는 콜론과 공백을 둡니다. (`feat: `)
2. `subject`는 50자 이내의 간결하고 명확한 어조로 작성합니다.
3. 끝에 마침표(`.`)를 붙이지 않습니다.
4. 한 커밋에는 가급적 하나의 논리적 작업 단위만 포함합니다.

### 커밋 메시지 예시
```bash
feat: Add onboarding API endpoint and nickname validation
feat: Implement map:sync broadcast in websocket manager
fix: Resolve null check on targetPlaceName
refactor: Separate Redis connection pool logic
docs: Update DB schema documentation
chore: Add asyncpg and aiosqlite to requirements
```

---

## 4. Pull Request (PR) 컨벤션

작업이 완료되면 `dev` 브랜치를 대상으로 PR을 생성합니다.

### PR 제목 형식
이슈 태그와 작업 내용, 그리고 연관 이슈 번호를 포함합니다.

```text
[Tag] 작업 내용 (#이슈번호)
```

### PR 제목 예시
```text
[Feat] 기기 등록 및 온보딩 API 구현 (#5)
[Feat] 실시간 소켓 위치 동기화 및 map:sync 브로드캐스트 (#9)
[Fix] 지각 시간 계산 시 타임존 오차 수정 (#12)
[Chore] Alembic 초기화 및 최초 테이블 마이그레이션 적용 (#1)
```

### PR 본문 작성 규칙
PR 템플릿 서식에 맞추어 아래 항목을 작성합니다:
1. `## 관련 이슈`: `Closes #5` 형식으로 자동 닫힘 키워드 명시
2. `## 변경 사항`: 주요 변경 및 추가된 코드 내용 요약
3. `## 테스트 및 확인 방법`: Swagger 호출, 소켓 테스트 클라이언트 결과 등 동작 검증 방식
4. `## 리뷰 요청 사항`: 리뷰어가 중점적으로 봐야 할 부분 기재

---

## 5. 실전 작업 흐름 예시 (Workflow)

```bash
# 1. 최신 dev 브랜치 이동 및 풀
git checkout dev
git pull origin dev

# 2. 작업 브랜치 생성 (예: #5번 이슈 기능 개발)
git checkout -b feature/5-user-onboarding

# 3. 코드 작성 후 커밋
git add .
git commit -m "feat: Implement POST /api/v1/users/onboarding endpoint"

# 4. 원격 브랜치로 푸시
git push origin feature/5-user-onboarding

# 5. GitHub에서 dev 브랜치 방향으로 PR 생성
# 제목: [Feat] 기기 등록 및 온보딩 API 구현 (#5)
# 본문: Closes #5 포함 후 리뷰 요청
```
