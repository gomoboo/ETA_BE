# 📍 이따 (ETA) 백엔드 개발 컨텍스트 & 에이전트 가이드

> 본 파일은 **'이따 (ETA - 실시간 약속 지각 방지 플랫폼)'** 백엔드 개발 시 AI 에이전트와 개발자가 반드시 준수하고 참고해야 하는 핵심 비즈니스 규칙, 팀원 간 연동 인터페이스, 진행 상태를 정리한 문서입니다.  
> Antigravity는 본 파일을 프로젝트 루트에서 자동으로 감지하여 최우선 지침으로 사용합니다.

---

## 1. 프로젝트 및 기술 스택 개요

- **서비스 컨셉**: 약속 시간에 늦거나 침대에서 거짓말하는 친구들을 실시간 위치 공유와 찌르기(Poke), 지각비 정산 및 **'지각 체포 영장'**으로 검거하는 소셜 지각 방지 플랫폼
- **Backend**: Python 3.12, FastAPI (비동기 async/await), Uvicorn
- **Database & ORM**: PostgreSQL / SQLite (Local), SQLAlchemy 2.0 (Async), Alembic
- **Real-time & In-Memory**: WebSocket, Redis (GEO & Caching)
- **External API**: Kakao Local API (장소 검색), FCM (푸시 알림)

---

## 2. 2인 협업 역할 분담

- **`@raewon12` (비즈니스 REST API 전담)**:
  - 공통 응답/예외(#2), 온보딩(#5), 약속 생성(#6), 초대/참여/퇴장(#7), 홈/대기실 조회(#8), 정산/영장(#12)
  - *현재 상태: 모든 PR(#16~#23) 완료 및 main 머지 완료*
- **`@leesk0007` (인프라 & 실시간 WebSocket 엔진 & DevOps 전담)**:
  - Redis 캐싱(#3), 웹소켓 위치 동기화(#9), 미출발 찌르기(#10), 지오펜싱 체크인(#11)
  - Docker/Compose(#13), CI/CD(#14), AI PR 리뷰 봇(#15)
  - *현재 상태: 진행 예정*

---

## 3. 완료된 구현 사항 및 확정된 비즈니스 규칙

### 3.1. 인증 및 공통 포맷
- **사용자 식별**: 회원가입 대신 요청 헤더 `X-Guest-UUID: {기기UUID}`를 사용하여 유저를 조회 (`app/api/deps.py`의 `get_current_user`).
- **공통 응답**: `{ "success": true, "data": { ... } }` 규격 준수.
- **예외 처리**: `AppException(ErrorCode.XXX)` 발생 시 `{ "success": false, "code": "...", "message": "..." }` 응답.

### 3.2. 확정된 핵심 도메인 규칙
1. **벌금 모드 명칭 통일 (`FEE`)**:
   - DB와 API 모두 **`penalty_type = 'FEE'`**로 통일됨 (`FINE` 요청 시 400 반환, 마이그레이션 `a752a1988286` 완료).
2. **약속 생성 및 초대 코드**:
   - `meetAt`은 미래 시간만 허용 (과거 시간 요청 시 400).
   - 6자리 영숫자 난수 초대코드 발급 (`ETA99K` 등), 방장은 `is_host=True`로 자동 참가 등록.
3. **방장 나가기 및 약속 취소**:
   - 방장이 나가면 가장 먼저 참여한 참가자에게 방장 위임.
   - 남은 참가자가 아무도 없으면 약속 상태를 `CANCELLED`로 변경.
4. **초대 링크 만료**:
   - 약속이 종료/취소되었거나 **약속 시간(`meetAt`)이 지나면 410 `INVITE_LINK_EXPIRED`** 반환.
5. **정산 및 지각 체포 영장 (#12)**:
   - **정산 가능 시점**: ① 약속이 `COMPLETED`이거나 ② 전원 도착했거나 ③ **약속 시간 + 60분**이 지났을 때만 정산 조회 가능 (그전에는 409 `SETTLEMENT_NOT_READY`).
   - **미도착자**: 끝까지 도착하지 않은 사람은 **60분 지각**으로 자동 간주하여 벌금 부과.
   - **지각 시간**: 초 단위는 **버림** 처리 (예: 18분 30초 지각 ➡️ 18분 지각).
   - **정산 확정 시점**: 정산 API가 처음 조회될 때 `COMPLETED` 상태로 갱신되고 결과가 고정됨.
   - **영장 발부**: 지각자가 한 명도 없으면 영장을 발부하지 않음 (API-10 404 반환).

---

## 4. WebSocket 개발 (`@leesk0007`) 필수 연동 규칙

웹소켓(#9, #10, #11)을 개발할 때 REST API와 데이터 정합성을 위해 반드시 아래 규격을 따릅니다:

### ① [#9] 소켓 연결 시 참가자 상태 검증
- 클라이언트가 `ws://.../ws/appointments/{appointment_id}?participant_id={id}` 접속 시, 해당 참가자가 **`join_status == 'JOINED'`** 상태인지 확인.
- 방 나가기(`POST /appointments/{id}/leave`)가 호출되면 서버에서 해당 유저의 웹소켓 연결을 즉시 끊도록 연동되어 있음.

### ② [#11] 도착 지오펜싱(50m) 체크인 시 저장 범위
- 참가자가 목적지 50m 반경에 진입하면 `participants` 테이블에 **`arrived_at = datetime.utcnow()`**와 **`arrival_status = 'EARLY' | 'ON_TIME' | 'LATE'`**만 저장하면 됨.
- *주의: 지각 시간(`final_late_minutes`)과 지각비(`final_fine_amount`)는 정산 서비스에서 자동 계산하므로 소켓 로직에서 별도로 계산할 필요 없음.*
- 체크인 완료 후 전원에게 `checkin:completed` 이벤트 브로드캐스트.

### ③ [#10] 미출발 찌르기 (Poke) 로깅
- 찌르기 전송 및 응답 시 `poke_logs` 테이블에 레코드를 저장.
- 정산 영장 생성 시 `poke_logs`를 조회하여 "응답하지 않은 찌르기 횟수"가 영장 판결문(*"및 찌르기 N회 무시 검거"*)에 자동 반영됨.

---

## 5. 현재 남아있는 작업 (TODO)

1. **#3 [Core]**: Redis 비동기 클라이언트 연동 및 위치 캐싱 모듈 (`app/core/redis.py`, `app/services/geo_service.py`)
2. **#9 [WebSocket]**: 실시간 소켓 연결 관리 및 위치 동기화 (`location:update` ➡️ `map:sync` 브로드캐스트)
3. **#10 [WebSocket]**: 5분 정지 미출발 감지 및 찌르기 실시간 이벤트 (`poke:send` ➡️ `poke:received` ➡️ `poke:respond`)
4. **#11 [WebSocket]**: Haversine 거리 계산, 50m 지오펜싱 도착 체크인 및 `checkin:completed` 브로드캐스트
5. **#13 [DevOps]**: 멀티스테이지 `Dockerfile` 및 `docker-compose.yml` (FastAPI + PostgreSQL + Redis)
6. **#14 [DevOps]**: GitHub Actions CI (린트/테스트) & CD (배포) 파이프라인
7. **#15 [DX/AI]**: GitHub Actions 기반 AI PR 자동 코드 리뷰 봇 연동
8. **후속 과제 (논의 필요)**: 외부 공유 링크(`shareUrl`)용 비인증 공개 조회 API 구현, 영장 카드 실제 이미지 생성 로직

---

## 6. 개발 및 협업 가이드라인

- **코드 컨벤션**: [docs/CONVENTION.md](docs/CONVENTION.md) 참조
  - 브랜치: `feature/<이슈번호>-<작업명>`
  - 커밋: `feat: ...`, `fix: ...`, `chore: ...`
  - PR: `[Feat] 작업 내용 (#이슈번호)` 및 본문에 `Closes #이슈번호` 명시
- **DB 스키마**: [docs/DB_SCHEMA.md](docs/DB_SCHEMA.md) 참조
  - 모델 변경 시 `alembic revision --autogenerate -m "..."` 마이그레이션 필수
