# 🚀낭만인프라 자동화 및 트러블슈팅 스크립트 저장소 (Nangman-Infra-Automation)

> **"인프라 운영을 가볍고, 안전하고, 낭만 있게."**
> 본 저장소는 단일 노드 Docker Compose 환경부터 중앙 집중형 액세스(Teleport), 낭만인프라 서비스 연동 및 모니터링 체인 구축 과정에서 작성한 인프라 자동화 스크립트와 트러블슈팅 가이드를 모아둔 개인 기술 아카이브입니다.

---

## 🛠️ 주요 프로젝트 및 스크립트 구성

### 1. 전사 멀티 서버 도커 서비스 일괄 점검 스크립트 (`/scripts/teleport-docker-check`)
- **개요:** 다수의 분산 서버에 위치한 Docker 서비스 현황을 수동 접속 없이 일괄 파악하기 위한 중앙 집중형 스크립트입니다.
- **핵심 기술:** Teleport CLI (`tsh`), Zsh 루프 및 조건문, Docker Engine CLI
- **기능:**
  - `tsh ls`로 타겟 서버 리스트를 동적으로 추출하고, `for loop` 기반으로 순차적/병렬적 원격 명령어 실행
  - 전수 조사 대상 서버들의 Docker 컨테이너 헬스체크(Up, Restarting, Exit) 상태를 1분 이내에 식별
  - 단일 노드 가용성 한계 및 SPOF(단일 장애점) 예측을 위한 베이스라인 데이터 수집

### 2. Huly 알림 Mattermost 전송 자동화 (`/scripts/huly-to-mattermost`)
- **개요:** 협업 툴 Huly에서 발생한 신규 이슈 및 알림을 사내 메신저인 Mattermost 채널로 실시간(주기적) 동기화하는 자동화 파이프라인입니다.
- **핵심 기술:** Python (`psycopg2`, `requests`), Docker Network, CockroachDB, Linux Crontab / n8n
- **특징 (보안 및 데이터 정제):**
  - **Docker 내부 네트워크 활용:** 외부 포트가 차단된 CockroachDB에 안전하게 접근하기 위해 Python 스크립트를 `huly_v7_huly_net` 내부 네트워크 전용 컨테이너로 실행
  - **Stateful 중복 방지 로직:** 5분 이내 생성된 신규 알림 중 발송 상태값 및 ID를 대조하여 중복 알림이 전송되는 현상 방지
  - **사용자 이름 매핑:** DB 내 `global_account.social_id`와 `person` 테이블을 `JOIN` 연산하여 UUID 형태의 데이터를 실제 이름(`first_name`, `last_name`)으로 정제하여 가독성 확보

### 3. Meetup(AWSKRUG) 새 글 알림 봇 (`/scripts/meetup-rss-bot`)
- **개요:** Meetup 페이지의 새로운 소식 및 이벤트 등록을 캐치하여 Mattermost 채널에 알림을 쏴주는 업무 자동화 스크립트입니다.
- **핵심 기술:** Python, Linux native package (`apt`), Mattermost Webhook
- **특징 (인프라 경량화):**
  - 서버 인프라를 가볍고 순정 상태로 유지하기 위해 무거운 `python3-pip` 패키지 전체를 설치하지 않고, 우분투 내장 패키지 매니저(`apt`)를 통해 `python3-requests` 라이브러리만 다이렉트로 주입하여 연동 구동

### 4. Docmost ➡️ Outline 문서 일괄 마이그레이션 (`/scripts/outline-migration`)
- **개요:** 사내 문서 도구를 Docmost에서 Outline으로 이전하기 위한 마크다운(Markdown) 및 이미지 자산 일괄 마이그레이션 스크립트입니다.
- **핵심 기술:** Python, Outline API
- **기능:**
  - 로컬의 복잡한 하위 폴더 구조(Grafana, TASK 등)와 마크다운 내 이미지 링크 관계를 깨뜨리지 않고 정형화하여 업로드
  - Outline API의 권한 수준(Admin/Member Key) 및 Collection ID와 Parent Document ID의 계층 구조 분석을 통한 오류 제어 예외 처리 포함

---

## 🔍 모니터링 & 인프라 아키텍처 가이드 (`/docs`)

스크립트 외에도 안정적인 운영을 위해 설계한 베이스라인과 대시보드 표준 가이드를 담고 있습니다.

- **서버 환경 베이스라인 & 준수 여부 프로세스:** 새 서버 추가 시 `Teleport`, `Zabbix-agent` 표준 설치 기준 정립 및 인프라 표준 패키지 준수 여부 자동 점검 가이드
- **글로벌 표준(USE/RED) 기반 모니터링 대시보드:**
  - **인프라(USE):** CPU, 메모리, 디스크 I/O Wait, 네트워크 가용량 체계화
  - **서비스 애플리케이션(RED):** Meet(네트워크 품질/동시접속), Docmost(DB 풀 성능), Mattermost(Conn Pool 포화도) 등 맞춤형 KPI 도출 및 Grafana 변수 활용 대시보드 설계법

---

## 🚨 주요 트러블슈팅 기록 (`/troubleshooting`)

- **Harbor 자동 재실행 및 의존성 꼬임 해결:** - Docker 데몬 재시작/업데이트 시 Core, Registry, DB 등 마이크로서비스 간의 부팅 순서가 어긋나 `Exit` 혹은 `Restarting` 루프에 빠지는 문제 분석
  - `docker-compose.yml` 내 `depends_on` 구조 최적화 및 `rsyslog_docker.conf` 바인드 마운트를 통한 로그 서비스 선행 안정화 조치 내용 수록
- **Ansible apt 업데이트 Mirror 서버 동기화 오류 조치:**
  - 미러 서버(`mirror.navercorp.com`)의 일시적 싱크 문제로 인한 해시값 불일치 오류 발생 시, `Ansible Ad-hoc` 명령어를 활용하여 수십 대 서버의 `apt` 캐시를 일괄 삭제 및 강제 초기화하는 긴급 복구 프로세스

---

## 🛠️ 아키텍처 환경 (Environment)
- **Access Control:** Teleport Proxy (tsh CLI 기반 인증서 로그인)
- **Network:** Amazon Route 53, WireGuard VPN (폐쇄망 구조), Nginx Proxy Manager (Reverse Proxy)
- **Storage & Backup:** Synology NAS (S3 호환 백엔드 저장소 활용 및 데이터 내구성 확보)
- **Virtualization:** Proxmox (KVM/LXC 기반 자가 호스팅 인프라 환경)

---
*본 저장소의 모든 스크립트와 가이드는 '낭만인프라'의 안정적인 인프라 운영 및 자동화를 위해 직접 테스트하고 검증한 결과물입니다.*
