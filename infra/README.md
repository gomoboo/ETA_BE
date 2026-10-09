# AWS 단일 서버: Terraform + 시작/중지 + 간단한 CD

관련 이슈: [#48](https://github.com/gomoboo/ETA_BE/issues/48). 서울 리전 EC2 한 대에서 API(워커 1개), PostgreSQL, Redis, Caddy를 실행한다. Terraform은 최초 인프라를 만들고, GitHub Actions는 **같은 인스턴스를 Stop/Start**한다. CD는 API 컨테이너만 교체한다. 실제 리소스 생성 및 AWS 시작/중지 검증은 계정 연결 이후 진행한다.

## 파일 구성

- `aws/`: VPC·서브넷·인터넷 게이트웨이·보안 그룹·EC2·EBS·고정 IP·ECR·IAM/OIDC Terraform, mock tests
- `docker/`: 서버용 Compose, Caddyfile, 환경변수 예제
- `scripts/`: 서버 최초 설치, 부팅, 이미지 교체, GitHub runner 시작/중지/CD 제어
- `../.github/workflows/aws-power.yml`: 수동 start / stop / status, 선택적 자동 중지
- `../.github/workflows/aws-cd.yml`: main CI 성공 후 SHA 이미지 게시 및 API 교체

## 사용자가 준비할 것

1. **AWS 계정과 결제 수단**, 리소스를 생성할 권한이 있는 AWS CLI 프로필. 계정 ID와 프로필 이름만 공유하면 된다. Access Key/비밀번호는 채팅이나 Git에 넣지 않는다.
2. 로컬 **Terraform 1.10 이상**과 **AWS CLI v2**. 예제의 `eta`는 본인의 프로필 이름으로 바꾼다. IAM Identity Center를 쓰면 `aws configure sso --profile eta`, `aws sso login --profile eta`로 로그인한다. 다른 인증 방식이라면 로컬 CLI에서만 설정한다.
3. **API 도메인** 및 DNS A 레코드 변경 권한. 도메인이 없으면 아래의 제한된 IP-only 임시 테스트 설정을 사용한다.
4. GitHub 저장소 Actions 변수를 설정할 권한. AWS 연결에는 OIDC 임시 자격 증명을 사용하며 장기 AWS 키를 GitHub Secrets에 저장하지 않는다.
5. 실제 카카오 REST API 키와 DB 비밀번호를 SSM SecureString에 입력할 준비. 초기 DB 비밀번호는 32-128자리 무작위 16진수로 만든다. API 키가 없으면 장소 검색은 실제 검증 대상에서 제외한다.

Terraform 실행 계정에는 EC2/VPC/EBS/EIP/ECR/SSM 구성, IAM 역할/정책/OIDC 생성 및 PassRole 권한이 필요하다. GitHub 역할에는 이 인스턴스의 시작/중지와 SSM 배포, 이 ECR 저장소의 이미지 게시 권한만 부여한다. 인프라 삭제 권한은 Actions에 부여하지 않는다. SSM 배포 명령은 대상 EC2 내에서 관리자 권한으로 실행되므로 main 브랜치 쓰기 권한을 제한한다.

## 1. 로그인과 환경변수 준비

```bash
export AWS_PROFILE=eta
export AWS_REGION=ap-northeast-2
aws sts get-caller-identity
cp infra/docker/.env.example infra/docker/.env.local
```

`.env.local`을 로컬 편집기로 채운다. 무작위 DB 비밀번호는 `openssl rand -hex 32`로 생성할 수 있다. 이미 DB가 초기화된 뒤에는 환경변수만 바꿔 DB 비밀번호를 변경하지 않는다. 먼저 PostgreSQL 내부 비밀번호를 함께 변경해야 한다.

실제 파일을 AWS SSM에 업로드한다. Terraform은 이 비밀 값을 읽거나 state에 저장하지 않는다.

```bash
aws ssm put-parameter --name /eta-test/backend-env --type SecureString \
  --value file://infra/docker/.env.local --overwrite
```

기본 AWS 관리 키 `aws/ssm`을 사용한다. 별도 고객 관리 KMS 키를 쓰려면 EC2 역할에 해당 키의 Decrypt 권한을 추가해야 한다. 프로젝트 이름을 바꾸면 SSM 경로도 맞춘다.

## 2. Terraform 최초 생성

먼저 이 인프라 코드를 main에 병합해야 한다. 기본 `code_ref=main`으로 VM이 공개 저장소의 설치 스크립트를 가져오기 때문이다.

```bash
cp infra/aws/terraform.tfvars.example infra/aws/terraform.tfvars
# terraform.tfvars에서 실제 도메인과 VM 사양을 입력한다.
terraform -chdir=infra/aws init
terraform -chdir=infra/aws plan
terraform -chdir=infra/aws apply
terraform -chdir=infra/aws output
```

`apply`는 실제 유료 리소스를 만든다. 미리 `plan`에서 대상 계정과 생성 목록을 확인한다. 기본 구성은 `t3.medium`, 암호화 gp3 30GiB, 온디맨드, CPU 크레딧 Standard다. 순간 부하에서 CPU가 제한될 수 있으며 최초 이미지 빌드는 시간이 걸릴 수 있다. NAT Gateway, 로드 밸런서, RDS를 생성하지 않는다.

출력한 `public_ip`에 도메인의 A 레코드를 연결한다. 외부에서는 80/443만 열고 API/DB/Redis는 공개하지 않는다. 80은 HTTPS 전환 및 인증서 발급에 사용한다. 관리 접속은 AWS Systems Manager Session Manager를 사용하며 SSH 키나 22번 포트는 필요 없다.

도메인이 없다면 처음부터 다음처럼 설정한다. 실제 테스트 기기의 공인 IP를 입력해야 하며 `0.0.0.0/0` HTTP는 검증에서 거부한다.

```hcl
api_domain        = ""
allow_plain_http  = true
allowed_web_cidrs = ["YOUR_PUBLIC_IP/32"]
```

IP-only HTTP는 임시 테스트용이다. 모바일의 평문 통신 허용 설정도 필요할 수 있다. 실사용 위치 데이터 연동에는 HTTPS/WSS 도메인을 설정한다. `api_domain` 등 bootstrap 설정은 최초 생성 때 고정된다. 기존 서버의 도메인을 변경할 때는 SSM에서 `/etc/eta/config.json`의 domain을 변경하고 `systemctl restart eta-backend.service`를 실행한다. Terraform 변수도 같은 값으로 유지한다. AMI와 user_data 업데이트는 기존 인스턴스를 자동 교체하거나 재시작하지 않는다.

AWS 계정에 GitHub OIDC 제공자가 이미 있으면 `existing_github_oidc_provider_arn`을 지정한다. 기본 신뢰 subject는 2026년 이후 생성한 이 저장소의 immutable owner/repository ID와 main 브랜치다. 포크나 다른 저장소에서는 공식 GitHub OIDC 문서에 따라 `repository`와 `github_oidc_subject`를 함께 변경한다. Environment를 추가하면 subject 형식도 바뀌므로 현재 워크플로에는 Environment를 지정하지 않는다.

## 3. GitHub Actions 연결

Terraform 출력에 나온 다음 5개를 저장소 **Settings → Secrets and variables → Actions → Variables**에 등록한다. 모두 비밀키가 아닌 리소스 식별자다.

| 변수 | Terraform 출력 |
|---|---|
| `AWS_REGION` | `aws_region` |
| `AWS_ROLE_ARN` | `actions_role_arn` |
| `AWS_INSTANCE_ID` | `instance_id` |
| `ECR_REPOSITORY` | `ecr_repository` |
| `IMAGE_PARAMETER` | `desired_image_parameter` |

`gh`에 로그인되어 있다면 한 번에 등록할 수도 있다.

```bash
terraform -chdir=infra/aws output -json github_variables > /tmp/eta-github-vars.json
python3 - <<'PY'
import json, subprocess
from pathlib import Path
for name, value in json.loads(Path('/tmp/eta-github-vars.json').read_text()).items():
    subprocess.run(['gh', 'variable', 'set', name, '--repo', 'gomoboo/ETA_BE', '--body', value], check=True)
PY
```

워크플로 파일이 main에 병합된 뒤 **Actions → AWS server power → Run workflow**에서 main 브랜치와 start / stop / status를 선택한다.

- `start`: stopped이면 시작, running이면 재부팅하지 않음. EC2 정상 상태와 SSM 온라인을 기다리고 앱 시작 및 로컬 `/health` 확인.
- `stop`: 정상 EC2 Stop 후 stopped까지 대기. 이미 stopped면 성공 처리. EBS와 고정 IP는 유지.
- `status`: 현재 EC2 상태 표시.
- 자동 중지: **기본 비활성화**. `AUTO_STOP_ENABLED=true`를 추가하면 현재 cron인 매일 **한국 시간 00:00**에 중지한다. 다른 시간은 workflow cron(UTC)을 수정한다. 자동 시작 스케줄은 없다. GitHub 예약 실행은 지연될 수 있어 정확한 비용 차단 시각을 보장하지 않는다.

Power와 CD는 같은 concurrency group을 사용해 시작/중지/배포가 겹치지 않는다. GitHub는 대기 실행을 교체할 수 있으므로 여러 요청의 처리 순서를 보장하지 않는다. 자동 중지 시간대에는 테스트를 피하고, Actions에서 실행 결과를 확인한다.

## 4. CD와 API 이미지 교체

main push의 **CI 성공 → GitHub에서 Docker 빌드 → ECR에 커밋 SHA 태그 게시 → SSM으로 API 교체** 순서다. 태그는 immutable이고 CI가 검증한 정확한 SHA를 checkout한다. 실패 CI/PR CI에서는 게시하지 않는다. 최초 VM 설치에 한해 공개 저장소를 clone하고 VM에서 bootstrap 이미지를 빌드한다.

서버가 running이면 `docker compose up -d --no-deps --no-build --wait api`로 API만 교체한다. DB/Redis와 볼륨은 유지한다. 새 API health가 실패하면 이전 로컬 이미지와 다음 부팅 이미지 선택을 복구하고 workflow를 실패 처리한다. **DB 마이그레이션은 되돌리지 않으므로 이전 이미지와 호환되는 스키마 변경만 적용해야 한다.**

서버가 stopped이면 이미지만 SSM의 비밀이 아닌 `desired-image` 값에 기록한다. 서버는 자동으로 켜지지 않는다. 다음 부팅에서 해당 이미지를 pull하고 DB/Redis/API/Caddy를 실행한다. pending/stopping에서는 CD가 실패하므로 power 작업 완료 뒤 재실행한다.

Actions의 **AWS simple CD → Run workflow**에서는 이미 ECR에 게시된 40자리 SHA를 지정해 재배포/이전 이미지 선택을 할 수 있다. 메모리의 WebSocket 연결은 컨테이너 교체 중 끊기므로 앱 재연결이 필요하다. EC2 재부팅, Kubernetes, GitOps는 사용하지 않는다. 인프라 스크립트 변경은 API 이미지에 포함되지 않으므로 필요하면 SSM에서 서버 checkout을 갱신하고 bootstrap을 재실행한다.

## 데이터 보존과 비용

컨테이너 데이터 볼륨은 EC2의 암호화 EBS에 저장된다. Stop/Start와 API 교체에는 보존되지만 백업을 대신하지는 않는다. 최초 실제 배포 전 EBS 스냅샷 또는 PostgreSQL dump 백업 주기를 설정한다. 삭제 방지는 기본 활성화지만 AWS 관리자에 의한 수동 삭제까지 막지는 않는다.

온디맨드 EC2 실행 요금은 중지하면 멈춘다. **EBS, Elastic IP, ECR 이미지와 백업 비용은 남는다.** 절전은 Terraform destroy가 아니다. 영구 정리하려면 백업 후 Terraform prevent_destroy와 EC2 termination protection을 해제해야 하고, 유지된 EBS/SSM 비밀 매개변수는 별도 확인해 정리한다. ECR의 기존 SHA 이미지는 수동 관리한다.

## 코드 검증과 실제 AWS 검증

AWS 계정 없이도 다음 검증은 가능하다. `terraform test`는 mock provider만 사용하며 AWS 리소스를 생성하지 않는다.

```bash
terraform -chdir=infra/aws init -backend=false
terraform -chdir=infra/aws fmt -check -recursive
terraform -chdir=infra/aws validate
terraform -chdir=infra/aws test
pytest -q
shellcheck infra/scripts/*.sh
POSTGRES_PASSWORD=ci-placeholder docker compose -f infra/docker/compose.yml config --quiet --no-env-resolution
```

계정 연결 후 실제 검증: 첫 부팅 `/health` → 테스트 약속 생성 → stop → start → 같은 약속 조회 → REST/WSS 휴대폰 두 대 → 새 API 이미지 배포 → DB 보존 → 실패 이미지 복구 → 꺼진 서버에 이미지 선택 후 다음 부팅 적용. 아직 실제 AWS 환경에서는 검증하지 않았다.

## Terraform state

처음은 한 명이 로컬 state를 관리한다. state와 tfvars는 Git에서 제외하며 **state를 잃지 않도록 별도로 보관한다**. 다른 PC에서 빈 state로 apply하면 중복 인프라를 만들 수 있다. 팀에서 인프라를 공동 변경할 때는 private/versioned S3 state bucket을 만들고 `aws/backend.tf.example`을 `backend.tf`로 복사한 뒤 `terraform init -migrate-state`로 옮긴다. S3 lockfile을 사용한다. Power/CD는 Terraform state를 읽거나 변경하지 않는다.

## 참고

- [EC2 Stop/Start](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Stop_Start.html)
- [GitHub AWS OIDC 및 immutable subject](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)
- [Terraform S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3)
- [Docker Ubuntu 설치](https://docs.docker.com/engine/install/ubuntu/)
