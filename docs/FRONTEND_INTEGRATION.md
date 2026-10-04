# 📱 이따 (ETA) 프론트엔드 연동 가이드

> ETA_FE(Flutter)에서 백엔드(REST API + WebSocket)를 연동할 때 참고하는 문서입니다.
> API 명세(REST API / WebSocket 명세)를 기준으로 하되, **명세에 없어서 백엔드에서 정한 규칙**은 ⚠️로 표시했습니다.

---

## 0. 한눈에 보기 (꼭 지켜야 할 것)

| # | 규칙 |
|---|---|
| 1 | 앱 첫 실행 시 **기기 UUID를 만들어 저장**하고, 이후 모든 요청에 `X-Guest-UUID` 헤더로 보냅니다. ⚠️ |
| 2 | 응답은 항상 `{"success": true/false, ...}` 형식입니다. 실패하면 **`code`로 분기**합니다. |
| 3 | 지각비 모드 값은 **`FEE`** 입니다. (`FINE`은 400 에러) |
| 4 | 시간은 모두 **UTC ISO 8601**(`2026-09-27T19:00:00Z`)입니다. 화면에 표시할 때 로컬 시간으로 변환하세요. |
| 5 | 웹소켓 접속 주소에 **`participant_id`와 `guestUuid`가 모두 필요**합니다. 내 `participantId`는 대기실 상세(API-07)의 **`myParticipantId`**로 받습니다. ⚠️ |
| 6 | 웹소켓 메시지는 **`{"type": "이벤트명", ...payload}`** 형식입니다. ⚠️ |
| 7 | 도착 자동 체크인 반경은 **30m** 입니다. |

---

## 1. 서버 주소

| 환경 | REST Base URL | WebSocket Base URL |
|---|---|---|
| 로컬 (iOS 시뮬레이터 / 웹) | `http://localhost:8000/api/v1` | `ws://localhost:8000/api/v1` |
| 로컬 (Android 에뮬레이터) | `http://10.0.2.2:8000/api/v1` | `ws://10.0.2.2:8000/api/v1` |
| 실기기 (같은 Wi-Fi) | `http://{PC의 IP}:8000/api/v1` | `ws://{PC의 IP}:8000/api/v1` |

로컬 백엔드 실행: 백엔드 레포에서 `docker compose up -d --build` → Swagger 문서 `http://localhost:8000/docs`

> Android에서 `http://`(평문) 통신을 하려면 개발 빌드의 `AndroidManifest.xml`에 `android:usesCleartextTraffic="true"`가 필요합니다.

---

## 2. 사용자 식별 (`X-Guest-UUID`) ⚠️

회원가입이 없고, **기기 UUID로 사용자를 구분**합니다.

1. 앱 첫 실행 시 UUID(v4)를 생성해 기기에 저장합니다. (예: `uuid` + `shared_preferences` 패키지)
2. 온보딩(API-01)에서 `guestUuid`로 등록합니다.
3. 이후 **모든 API 요청 헤더**에 `X-Guest-UUID: {저장한 UUID}`를 넣습니다.
   - 헤더가 없으면 `401 UNAUTHORIZED`, 온보딩하지 않은 UUID면 `404 USER_NOT_FOUND`
   - `USER_NOT_FOUND`를 받으면 온보딩 화면으로 보내면 됩니다.
4. 앱을 지우면 UUID도 사라져서 새 사용자가 됩니다.

> 헤더가 필요 없는 API: 온보딩(API-01), 장소 검색(API-03), 초대 링크 미리보기(API-05)

---

## 3. 공통 응답 형식

**성공**
```json
{ "success": true, "data": { ... }, "message": null }
```

**실패**
```json
{ "success": false, "code": "INVITE_LINK_EXPIRED", "message": "만료된 초대 링크입니다.", "data": null }
```

**입력값 검증 실패(400 `INVALID_INPUT`)** 때는 `data`에 필드별 사유가 들어옵니다.
```json
{
  "success": false, "code": "INVALID_INPUT", "message": "요청 값이 올바르지 않습니다.",
  "data": [ { "field": "meetAt", "reason": "약속 시간은 현재 이후여야 합니다." } ]
}
```

### 에러 코드

| HTTP | code | 언제 | 앱 처리 예시 |
|---|---|---|---|
| 400 | `INVALID_INPUT` | 필수값 누락, 형식 오류, 검증 실패 | `data[].reason` 표시 |
| 400 | `INVALID_NICKNAME_LENGTH` | 닉네임 2~10자 위반 (앞뒤 공백 제외 후) | 닉네임 입력란 에러 |
| 401 | `UNAUTHORIZED` | `X-Guest-UUID` 헤더 없음 | UUID 저장 로직 확인 |
| 403 | `NOT_PARTICIPANT` | 참여하지 않은(또는 나간) 약속에 접근 | 홈으로 이동 |
| 404 | `USER_NOT_FOUND` | 온보딩하지 않은 UUID | 온보딩 화면으로 |
| 404 | `APPOINTMENT_NOT_FOUND` | 없는 약속 | 안내 후 홈으로 |
| 404 | `INVITE_CODE_NOT_FOUND` | 없는 초대 코드 | "유효하지 않은 초대 링크" |
| 404 | `WARRANT_NOT_FOUND` | 지각자가 없어 영장 없음 | "전원 정시 도착!" 화면 |
| 404 | `POKE_NOT_FOUND` | (웹소켓) 없는/내 것이 아닌 찌르기 | 팝업 닫기 |
| 409 | `ALREADY_JOINED` | 이미 참여 중인 약속에 다시 참여 | 대기실로 바로 이동 |
| 409 | `APPOINTMENT_ALREADY_ENDED` | 종료/취소된 약속에서 나가기 등 | 결과 화면 또는 홈 |
| 409 | `SETTLEMENT_NOT_READY` | 아직 정산 조건이 안 됨, 취소된 약속 | 잠시 후 재시도 |
| 409 | `RADAR_NOT_STARTED` | (웹소켓) 레이더 시작 전 위치 전송 | 시작 시각까지 대기 |
| 409 | `CONFLICT` | (웹소켓) 이미 응답한 찌르기, 도착한 사람 찌르기 | 안내 |
| 410 | `INVITE_LINK_EXPIRED` | 종료·취소됐거나 **약속 시간이 지난** 초대 링크 ⚠️ | "만료된 초대 링크" |
| 502 | `KAKAO_API_ERROR` | 카카오 장소 검색 실패 | "잠시 후 다시 검색" |
| 500 | `INTERNAL_SERVER_ERROR` | 서버 오류 | 공통 에러 화면 |

---

## 4. 화면별 호출 흐름

```
[앱 첫 실행] UUID 생성·저장 → API-01 온보딩
[홈]        API-02 홈 목록
[약속 만들기] API-03 장소 검색 → API-04 약속 생성 → inviteUrl 공유
[초대 링크 열기] API-05 미리보기(헤더 불필요) → (온보딩 안 했으면 API-01) → API-06 참여
[대기실]     API-07 상세 (remainingSecondsToRadar로 카운트다운, myParticipantId 저장) / API-08 나가기
[레이더]     radarStartAt 이후 WebSocket 접속 → location:update 주기 전송 → map:sync 수신
            찌르기 poke:send / poke:received / poke:respond, 도착하면 checkin:completed
[결과]       API-09 정산 → API-10 영장(404면 영장 없음)
```

---

## 5. REST API

> 요청/응답 필드는 `docs/specs`의 REST API 명세와 같습니다. 아래는 **검증 규칙과 명세에 없는 동작** 위주로 정리했습니다.

### [API-01] 기기 등록 및 온보딩 — `POST /users/onboarding` (헤더 불필요)
```json
// Request
{ "guestUuid": "550e8400-...", "nickname": "지민", "profileCharacter": "char_rabbit",
  "locationTermsAgreed": true, "notificationAllowed": true, "fcmToken": "..." }
// Response data
{ "userId": 101, "nickname": "지민", "locationTermsAgreed": true }
```
- `guestUuid`, `nickname`만 필수입니다. 같은 UUID로 다시 호출하면 **정보를 갱신**합니다(닉네임 변경에도 사용 가능).
- 갱신할 때 `profileCharacter`, `fcmToken`을 생략하면 기존 값을 유지합니다.
- 닉네임은 앞뒤 공백을 제거한 뒤 2~10자인지 검사합니다.

### [API-02] 홈 약속 목록 — `GET /appointments/home`
- 내가 **참여 중(JOINED)**이고 **종료·취소되지 않은** 약속만 `meetAt` 순으로 반환합니다.
- `activeAppointments`: 레이더 시작 시각(`radarStartAt`)이 지난 약속, `isLocationSharingActive: true`
- `upcomingAppointments`: 아직 레이더 시작 전
- `participantCount`: 나간 사람을 제외한 인원
- 정산 API를 조회했거나 전원 도착한 약속은 `COMPLETED`가 되어 목록에서 빠집니다.

### [API-03] 장소 검색 — `GET /places/search?query=강남역` (헤더 불필요)
- 최대 15개를 반환합니다. `address`는 도로명 주소를 우선 쓰고, 없으면 지번 주소를 씁니다.
- 결과의 `placeName`, `address`, `latitude`, `longitude`를 API-04의 `targetPlaceName`, `targetAddress`, `targetLatitude`, `targetLongitude`에 그대로 넣으면 됩니다.

### [API-04] 약속 생성 — `POST /appointments`
```json
{
  "title": "강남역 맛집 탐방",
  "targetPlaceName": "스타벅스 강남역점", "targetAddress": "서울 강남구 강남대로 396",
  "targetLatitude": 37.497952, "targetLongitude": 127.027619,
  "meetAt": "2026-09-27T19:00:00Z",
  "radarStartType": "30M_BEFORE", "customRadarMinutesBefore": null,
  "penaltyType": "PENALTY", "penaltyContent": "커피 쏘기", "finePerMinute": 0
}
```
| 필드 | 규칙 |
|---|---|
| `meetAt` | **현재 이후**만 가능. 시간대를 포함해서 보내면 UTC로 변환합니다(`+09:00` 가능) |
| `radarStartType` | `10M_BEFORE`, `20M_BEFORE`, `30M_BEFORE`(기본), `1H_BEFORE`, `CUSTOM` |
| `customRadarMinutesBefore` | `CUSTOM`일 때만 **필수**(1~1440분), 그 외에는 무시 |
| `penaltyType` | `PENALTY`(벌칙): `penaltyContent` **필수**, `finePerMinute`는 0으로 저장 |
| | **`FEE`**(지각비): `finePerMinute` **1 이상 필수**, `penaltyContent`는 비움 |

- 응답의 `inviteUrl`(`https://eta.app/invite/{inviteCode}`)을 공유하면 됩니다. 초대 코드는 6자리 대문자+숫자입니다.
- 만든 사람은 자동으로 **방장(isHost)**으로 참여합니다.

### [API-05] 초대 링크 미리보기 — `GET /appointments/invite/{inviteCode}` (헤더 불필요)
- 온보딩 전 사용자도 볼 수 있습니다. 초대 코드는 대소문자를 구분하지 않습니다.
- `penaltySummary`: `"벌칙: 커피 쏘기"` / `"지각비: 분당 1,000원"`
- `radarStartSummary`: `"약속 30분 전부터 위치 공유 시작"` / `"약속 1시간 30분 전부터 ..."`
- ⚠️ **약속이 종료·취소됐거나 약속 시간이 지났으면** `410 INVITE_LINK_EXPIRED`

### [API-06] 약속 참여 — `POST /appointments/invite/{inviteCode}/join`
```json
{ "nickname": "민수" }   // 생략하면({}) 온보딩 닉네임 사용
```
- 이미 참여 중이면 `409 ALREADY_JOINED` → 대기실로 이동하면 됩니다.
- ⚠️ **나갔던 약속에는 다시 참여할 수 있습니다**(같은 `participantId` 유지).

### [API-07] 대기실 상세 — `GET /appointments/{appointmentId}`
- **참여 중인 사람만** 조회할 수 있습니다(아니면 `403 NOT_PARTICIPANT`).
- `remainingSecondsToRadar`: 요청 시점 기준 레이더 시작까지 남은 초입니다. 이미 시작했으면 0이에요. 받은 뒤에는 앱에서 1초씩 줄이며 표시하면 됩니다.
- `participants`: 참여 중인 사람만, **방장 먼저 → 참여 순**
- ⚠️ **`myParticipantId`**(명세 외 추가 필드): 요청한 **내 `participantId`**입니다. 웹소켓 접속에 이 값을 쓰세요. 방장은 약속 생성 응답에 `participantId`가 없어서 여기서 받아야 합니다.

### [API-08] 약속 나가기 — `POST /appointments/{appointmentId}/leave`
- 나가면 **웹소켓 연결이 서버에서 끊기고** 정산에서 제외됩니다.
- ⚠️ 방장이 나가면 **가장 먼저 참여한 사람이 새 방장**이 됩니다. 아무도 안 남으면 약속이 **취소(`CANCELLED`)**됩니다.
- 종료·취소된 약속에서는 `409 APPOINTMENT_ALREADY_ENDED`

### [API-09] 정산 결과 — `GET /appointments/{appointmentId}/settlement`
- ⚠️ 정산은 **① 전원 도착(체크인) ② 약속 시간 + 60분 경과 ③ 이미 완료된 약속** 중 하나일 때만 가능합니다. 그 전에는 `409 SETTLEMENT_NOT_READY`
- ⚠️ 지각 시간은 **분 단위 버림**입니다(18분 30초 → 18분). **끝까지 도착하지 않은 사람은 60분 지각**으로 처리합니다.
- 지각비: `FEE` 모드는 `지각 분 × finePerMinute`, `PENALTY` 모드는 항상 0
- 처음 조회할 때 결과가 확정되고, 이후에는 같은 결과를 돌려줍니다.
- `arrivalStatus`: `EARLY` / `ON_TIME` / `LATE` / `NOT_ARRIVED`(미도착)

### [API-10] 지각 체포 영장 — `GET /appointments/{appointmentId}/warrant`
- 지각 시간이 가장 긴 사람이 대상입니다. **지각자가 없으면 `404 WARRANT_NOT_FOUND`** → "전원 정시 도착" 화면으로 처리하세요.
- 미도착자가 대상이면 `chargeTitle`이 `"약속 장소 무단 미도착죄"`입니다.
- `judgmentText` 예: `"약속 시간 18분 초과 및 찌르기 2회 무시 검거"`
- ⚠️ `shareCardImageUrl`은 **URL 형식만 있고 실제 이미지는 아직 생성되지 않습니다.** 당분간 카드는 앱에서 직접 그려주세요.

---

## 6. WebSocket (실시간 레이더)

### 6.1 접속 ⚠️
```
ws://{host}/api/v1/ws/appointments/{appointmentId}?participant_id={myParticipantId}&guestUuid={기기 UUID}
```
- `guestUuid` 대신 `X-Guest-UUID` 헤더를 써도 됩니다.
- 아래 경우 서버가 **close code `1008`**로 연결을 거부합니다. 참여하지 않았거나 나간 약속, 다른 사람의 `participant_id`, 종료·취소된 약속, `guestUuid` 누락.
- 같은 참가자가 다시 접속하면 **이전 연결은 서버가 닫습니다.** 앱이 백그라운드에서 돌아올 때 재접속하면 됩니다.
- 접속은 언제든 가능하지만, **위치 전송은 `radarStartAt` 이후부터** 받습니다.

### 6.2 메시지 형식 ⚠️
명세의 payload에 **`type`** 필드를 더한 JSON 한 개입니다.
```json
{ "type": "location:update", "latitude": 37.491234, "longitude": 127.021111, "speedKmh": 14.5 }
```
- 명세의 `appointmentId`, `participantId`는 접속 주소에 이미 있어서 **생략 가능**합니다. 보낼 경우 접속 정보와 같아야 합니다.
- 처리 중 오류는 아래 형식으로 받고, **연결은 유지됩니다.**
  ```json
  { "type": "error", "code": "RADAR_NOT_STARTED", "message": "아직 위치 공유(레이더)가 시작되지 않았습니다." }
  ```

### 6.3 보내는 이벤트 (Client → Server)

| type | payload | 설명 |
|---|---|---|
| `location:update` | `latitude`, `longitude`, `speedKmh`(0 이상, 생략 시 0) | 몇 초 간격으로 계속 보냅니다(3~10초 권장) |
| `poke:send` | `targetParticipantId` | 자기 자신·도착한 사람·다른 약속 참가자는 불가 |
| `poke:respond` | `pokeId`, `action` | `action`은 **`NOW_DEPARTING`** 또는 **`DISMISSED`**, 한 번만 응답 가능 |

### 6.4 받는 이벤트 (Server → Client)

| type | 언제 | 받는 사람 |
|---|---|---|
| `map:sync` | **누군가 위치를 보낼 때마다** ⚠️ (별도 주기 없음) | 방 전체 |
| `poke:received` | 누가 나를 찔렀을 때 | 대상자만 |
| `checkin:completed` | 누가 목적지 **30m 안**에 들어왔을 때 | 방 전체 |
| `error` | 내가 보낸 메시지 처리 실패 | 보낸 사람만 |

**`map:sync`** — 명세와 같고, 아래만 참고하세요.
- `participants`에는 **위치를 한 번이라도 보낸 사람만** 들어옵니다. 아직 위치가 없는 참가자는 대기실 목록(API-07)으로 표시하세요.
- ⚠️ `movementState` 값

  | 값 | 의미 |
  |---|---|
  | `MOVING` | 이동 중 |
  | `STOPPED` | 잠깐 멈춤(속도 2km/h 이하, 5분 미만) — **명세에 없음** |
  | `SUSPECTED_NOT_DEPARTED` | 같은 자리(반경 15m)에 5분 이상 → **찌르기 대상** |
  | `LATE` | 약속 시간이 지났는데 이동 중 — **명세에 없음** |
  | `ARRIVED` | 체크인 완료 — **명세에 없음** |
- `lateElapsedSeconds`: 약속 시간 이후 지난 초입니다. 도착한 사람은 도착 시각 기준으로 고정돼요.
- `currentAccruedFine`: `FEE` 모드에서 지금까지 쌓인 지각비(`지난 분 × 분당 금액`)입니다. `PENALTY` 모드는 0이에요.
- `estimatedArrivalMinutes`: 속도가 2km/h 이하면 `null`

**`poke:received`** — 명세와 같습니다. `remainingDistanceMeter`는 대상의 위치가 아직 없으면 `null`입니다.
> ⚠️ 대상이 **앱을 꺼서 접속 중이 아니면 알림이 가지 않습니다**(FCM 푸시 미구현, 기록만 남음). 보낸 사람에게는 별도 응답이 없습니다.

**`checkin:completed`** — 명세와 같습니다.
- ⚠️ `arrivalStatus` 기준: 약속 **1분 전보다 일찍** 도착하면 `EARLY`, **1분 이상 늦으면** `LATE`, 그 사이는 `ON_TIME`
- 이 메시지 바로 뒤에 `map:sync`가 이어서 옵니다.
- **전원이 체크인하면 약속이 완료(`COMPLETED`)**되고, 이후 위치 전송은 `APPOINTMENT_ALREADY_ENDED` 에러가 납니다. 이때 정산 화면(API-09)으로 이동하세요.

---

## 7. Flutter 예시 코드

`pubspec.yaml`
```yaml
dependencies:
  http: ^1.6.0
  web_socket_channel: ^3.0.0
  uuid: ^4.5.0
  shared_preferences: ^2.3.0
```

**기기 UUID와 API 호출**
```dart
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

const baseUrl = 'http://10.0.2.2:8000/api/v1'; // Android 에뮬레이터 기준

Future<String> getGuestUuid() async {
  final prefs = await SharedPreferences.getInstance();
  final saved = prefs.getString('guestUuid');
  if (saved != null) return saved;

  final id = const Uuid().v4(); // 첫 실행 시 한 번만 생성
  await prefs.setString('guestUuid', id);
  return id;
}

class ApiException implements Exception {
  ApiException(this.statusCode, this.code, this.message, this.data);
  final int statusCode;
  final String code;
  final String message;
  final dynamic data; // INVALID_INPUT일 때 [{field, reason}]
}

Future<Map<String, dynamic>> api(String method, String path, {Map<String, dynamic>? body}) async {
  final request = http.Request(method, Uri.parse('$baseUrl$path'))
    ..headers['Content-Type'] = 'application/json'
    ..headers['X-Guest-UUID'] = await getGuestUuid();
  if (body != null) request.body = jsonEncode(body);

  final response = await http.Response.fromStream(await request.send());
  final json = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  if (json['success'] != true) {
    throw ApiException(response.statusCode, json['code'], json['message'], json['data']);
  }
  return json['data'] as Map<String, dynamic>;
}

// 사용 예
// await api('POST', '/users/onboarding', body: {'guestUuid': await getGuestUuid(), 'nickname': '지민'});
// final home = await api('GET', '/appointments/home');
```

**레이더 웹소켓**
```dart
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';

Future<WebSocketChannel> connectRadar(int appointmentId, int participantId) async {
  final uri = Uri.parse(
    'ws://10.0.2.2:8000/api/v1/ws/appointments/$appointmentId'
    '?participant_id=$participantId&guestUuid=${await getGuestUuid()}',
  );
  final channel = WebSocketChannel.connect(uri);

  channel.stream.listen((raw) {
    final message = jsonDecode(raw as String) as Map<String, dynamic>;
    switch (message['type']) {
      case 'map:sync':          /* 친구 마커·거리·상태 갱신 (message['participants']) */ break;
      case 'poke:received':     /* 찌르기 팝업 표시 (message['pokeId']) */ break;
      case 'checkin:completed': /* 도착 토스트, 전원 도착이면 정산 화면으로 */ break;
      case 'error':             /* message['code']로 분기 */ break;
    }
  }, onDone: () {
    // channel.closeCode == 1008 이면 접속 권한 없음(나간 약속 등)
  });
  return channel;
}

void sendLocation(WebSocketChannel channel, double lat, double lng, double speedKmh) {
  channel.sink.add(jsonEncode({'type': 'location:update', 'latitude': lat, 'longitude': lng, 'speedKmh': speedKmh}));
}

void sendPoke(WebSocketChannel channel, int targetParticipantId) {
  channel.sink.add(jsonEncode({'type': 'poke:send', 'targetParticipantId': targetParticipantId}));
}

void respondPoke(WebSocketChannel channel, int pokeId, {required bool departing}) {
  channel.sink.add(jsonEncode({'type': 'poke:respond', 'pokeId': pokeId, 'action': departing ? 'NOW_DEPARTING' : 'DISMISSED'}));
}
```
> `geolocator`의 `Position.speed`는 **m/s** 단위입니다. `speedKmh = position.speed * 3.6`으로 변환해서 보내세요(음수면 0).

---

## 8. 아직 지원하지 않는 것

| 기능 | 상태 |
|---|---|
| FCM 푸시(앱이 꺼져 있을 때 찌르기 알림) | 미구현 — 앱 실행 중에만 `poke:received` 수신 |
| 영장 카드 이미지(`shareCardImageUrl`) | URL만 있고 이미지 없음 |
| 외부 공유 웹페이지용 공개 조회 API | 미구현 — 정산·영장은 참여자만 조회 가능 |
| 찌르기 횟수 제한 | 없음 |
