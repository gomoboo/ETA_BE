# 📍 이따 (ETA - Estimated Time of Arrival) Backend

> **"아직 침대면서 '지금 가는 중'이라고 거짓말하는 친구들을 검거하는 실시간 약속 지각 방지 플랫폼"**

FastAPI와 WebSocket을 기반으로 제작된 실시간 위치 공유 및 지각비 정산 백엔드 서비스입니다.

---

## 📁 디렉터리 구조 (Directory Structure)

```text
gomoboo/
├── app/
│   ├── main.py                  # FastAPI 앱 엔트리포인트 & CORS 설정
│   ├── core/                    # 프로젝트 핵심 모듈 (설정, 웹소켓 매니저, DB 설정)
│   │   ├── config.py
│   │   └── websocket_manager.py
│   ├── models/                  # SQLAlchemy DB 엔티티 모델
│   │   ├── user.py
│   │   ├── appointment.py
│   │   └── settlement.py
│   ├── schemas/                 # Pydantic 요청/응답 검증 스키마
│   │   ├── common.py
│   │   └── websocket.py
│   ├── api/
│   │   └── v1/
│   │       ├── router.py        # v1 라우터 통합
│   │       └── endpoints/       # 기능별 API 엔드포인트
│   │           ├── users.py         # [API-01] 온보딩
│   │           ├── places.py        # [API-03] 카카오 장소 검색
│   │           ├── appointments.py  # [API-02, 04, 05, 06, 07, 08] 약속 관리
│   │           ├── settlement.py    # [API-09, 10] 정산 및 지각 체포 영장
│   │           └── websocket.py     # [WS-01 ~ 06] 실시간 위치/찌르기/체크인
│   └── services/                # 비즈니스 로직 (거리 계산, Redis GEO, 푸시 알림)
│       ├── geo_service.py
│       └── kakao_place_service.py
├── docs/                        # 상세 기획 및 API/WebSocket 명세서
│   └── specs/
│       ├── 1_REST_API_명세서.csv
│       ├── 2_WebSocket_명세서.csv
│       └── notion_export/
├── .env.example                 # 환경 변수 템플릿
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 🛠️ 기술 스택 (Tech Stack)

* **Backend**: Python 3.12+, FastAPI, Uvicorn
* **Database & ORM**: PostgreSQL / SQLite (Local), SQLAlchemy (Async), Alembic
* **Real-time & Cache**: WebSocket, Redis (GEO & Caching)
* **External APIs**: Kakao Local API (장소 검색), Firebase Cloud Messaging (FCM 알림)

---

## 🐳 Docker로 실행 (API + PostgreSQL + Redis)

```bash
docker compose up -d --build     # 빌드 후 실행 (시작 시 alembic upgrade head 자동 적용)
docker compose logs -f api       # 로그 확인
docker compose down              # 종료 (데이터 유지)
docker compose down -v           # 종료 + 데이터 삭제
```
* API: `http://localhost:8000` (Swagger `/docs`, 헬스체크 `/health`)
* `.env`가 있으면 읽어서 사용하고(카카오 키 등), `DATABASE_URL`과 `REDIS_URL`은 컨테이너 내부 주소로 자동 설정됩니다.
* DB 계정은 `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` 환경 변수로 바꿀 수 있습니다(기본값 `eta`).
* 웹소켓 연결을 프로세스 메모리에서 관리하므로 **API는 워커 1개로 실행**합니다. 여러 인스턴스로 늘리려면 Redis Pub/Sub 기반 브로드캐스트가 필요합니다.

---

## 🚀 로컬 실행 방법 (Getting Started)

### 1. 가상환경 생성 및 패키지 설치
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 환경 변수 설정
```bash
cp .env.example .env
```

### 3. DB 마이그레이션 적용
`.env`의 `DATABASE_URL` 기준으로 테이블을 생성합니다.
```bash
alembic upgrade head
```

모델(`app/models/`)을 수정했다면 마이그레이션 파일을 생성한 뒤 적용합니다.
```bash
alembic revision --autogenerate -m "변경 내용 요약"
alembic upgrade head
```
* 생성된 파일(`alembic/versions/`)은 커밋 전에 내용을 꼭 확인해주세요.
* 되돌리기: `alembic downgrade -1`

### 4. 테스트 실행
```bash
pip install -r requirements-dev.txt
pytest
ruff check .
```
* 테스트마다 임시 SQLite DB를 새로 만들어 사용하므로 별도 DB나 Redis 설정이 필요 없습니다.
* PR과 `main`/`dev` push 시 GitHub Actions CI(`.github/workflows/ci.yml`)가 린트, 테스트, PostgreSQL 마이그레이션 검사를 자동으로 실행합니다.

### 5. 서버 실행
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
* Swagger API 문서: `http://localhost:8000/docs`
* 헬스 체크: `http://localhost:8000/health`
* DB 스키마 및 데이터 사전: [docs/DB_SCHEMA.md](docs/DB_SCHEMA.md)
* 협업 컨벤션 가이드: [docs/CONVENTION.md](docs/CONVENTION.md)
