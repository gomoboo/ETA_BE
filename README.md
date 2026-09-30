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

## 👥 2인 협업 분업 가이드 (Role & Responsibilities)

단순히 "REST vs WebSocket"으로만 나누면 **User, Appointment 등 공통 DB 모델 및 데이터 의존성** 때문에 한쪽이 대기하거나 충돌이 발생하기 쉽습니다. 따라서 **사전 공통 작업 후 역할 분담**을 권장합니다.

### 0단계: 공통 협업 (Day 1 필수)
- **DB 테이블 및 공통 모델 정의**: `User`, `Appointment`, `Participant`, `PokeLog`, `Settlement` 테이블의 스키마와 타입을 함께 확정합니다.
- Git 브랜치 전략 협의 (`main` <- `dev` <- `feature/xxx`)

### 역할 분담 추천안 (도메인 & 엔진 분리)

| 구분 | 개발자 A (비즈니스 라이프사이클 담당) | 개발자 B (실시간 트래킹 & 엔진 담당) |
| :--- | :--- | :--- |
| **주요 역할** | **REST API 전반 & 외부 연동 & 데이터 영속화** | **WebSocket 실시간 엔진 & 인메모리(Redis) 처리** |
| **담당 엔드포인트** | • `[API-01]` 기기 등록 및 온보딩<br>• `[API-02]` 홈 화면 약속 목록 조회<br>• `[API-03]` 카카오 장소 키워드 검색<br>• `[API-04~08]` 약속 생성, 초대, 대기실<br>• `[API-09~10]` 정산 및 지각 체포 영장 발부 | • `[WS-01]` 위치/속도 실시간 수신<br>• `[WS-02]` 지도 및 참가자 상태 브로드캐스트 (`map:sync`)<br>• `[WS-03~05]` 미출발 찌르기 (`poke:send/received`)<br>• `[WS-06]` 목적지 반경 자동 체크인 |
| **핵심 기술 스택** | FastAPI Router, SQLAlchemy/Alembic, Kakao API, 정산 알고리즘 | WebSocket, Redis (GEO & Pub/Sub), Geopy (거리/지오펜싱), 미출발 감지 로직 |
| **이점** | 앱의 시작과 끝(온보딩, 생성, 결과)을 완결성 있게 구축 | 실시간 성능과 소켓 통신 완성도에 온전히 집중 가능 |

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

### 3. 서버 실행
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- Swagger API 문서: `http://localhost:8000/docs`
- 헬스 체크: `http://localhost:8000/health`
# ETA_BE
