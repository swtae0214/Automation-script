import psycopg2
import requests
import time
import os
import json

# ==========================================
# 1. 환경 설정 및 민감 정보 분리
# ==========================================
# 실제 접속 정보는 환경 변수(Environment Variable)에서 안전하게 로드합니다.
# 값이 없을 경우 시스템이 중단되지 않도록 기본(Fallback) 더미 주소를 지정합니다.
DB_URL = os.environ.get("DB_URL", "postgresql://username:password@localhost:5432/database")
MATTERMOST_WEBHOOK = os.environ.get("MATTERMOST_WEBHOOK", "https://mattermost.example.com/hooks/xxxx")

# 알림을 이미 보낸 이슈 ID 목록을 저장할 로컬 파일 경로
SENT_IDS_FILE = "./sent_ids.json"

# 데이터베이스 내부의 우선순위 코드(0~4)를 가독성 좋은 문자열로 매핑
PRIORITY_MAP = {
    "0": "No priority",
    "1": "Urgent",
    "2": "High",
    "3": "Medium",
    "4": "Low"
}

# 데이터베이스 상의 사용자 이름 혹은 ID를 Mattermost 멘션 계정명으로 변환하는 매핑 테이블
# 오픈소스 배포 시에는 예시 데이터로 치환하여 보관합니다.
MENTION_MAP = {
    "홍길동": "@GildongHong"
}

# ==========================================
# 2. 유틸리티 함수 (파일 I/O 및 데이터 가공)
# ==========================================

def load_sent_ids():
    """이미 알림이 전송된 고유 ID 목록을 로컬 JSON 파일에서 읽어와 Set 형태로 반환합니다."""
    if os.path.exists(SENT_IDS_FILE):
        try:
            with open(SENT_IDS_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 파일 로드 실패 (새로 생성함): {e}")
    return set()

def save_sent_ids(sent_ids):
    """중복 전송을 방지하기 위해 갱신된 전송 완료 ID 목록을 파일에 저장합니다."""
    try:
        with open(SENT_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(sent_ids), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 파일 저장 실패: {e}")

def get_mention(name):
    """사용자 이름을 기반으로 MENTION_MAP을 조회하여 Mattermost 멘션 태그를 반환합니다."""
    if not name:
        return "담당자 없음"
        
    for key, mention in MENTION_MAP.items():
        if key in name:
            return mention
    return name  # 매핑된 계정이 없으면 원래 이름을 그대로 반환

# ==========================================
# 3. 데이터베이스(DB) 데이터 조회 함수
# ==========================================

def get_person_name(cur, account_id):
    """사용자 ID(account_id)를 기반으로 데이터베이스 내 사용자 실명을 조회합니다."""
    if not account_id:
        return "Unknown"
    
    try:
        # 오픈소스용 표준 스키마 예시로 추상화된 쿼리문
        # 1차 조회: 회원 고유 프로필 및 계정 연동 테이블 조회
        cur.execute("""
            SELECT u.first_name, u.last_name
            FROM member.account_profile u
            WHERE u.account_id::text = %s
            LIMIT 1
        """, (str(account_id),))
        row = cur.fetchone()
        if row:
            first, last = row
            return f"{last} {first}".strip() if last else first
        
        # 2차 조회: 1차 결과가 없을 경우 주소록 이력 테이블에서 이름 추출
        cur.execute("""
            SELECT name
            FROM public.contacts
            WHERE id = %s
            LIMIT 1
        """, (str(account_id),))
        row = cur.fetchone()
        if row and row[0]:
            return row[0].strip(",").strip()
            
    except Exception as e:
        print(f"사용자 이름 조회 중 오류 발생 (ID: {account_id}): {e}")
        
    return str(account_id)  # 조회 실패 시 고유 ID 자체를 문자열로 반환

def get_new_issues():
    """최근 5분 이내에 데이터베이스에 새로 등록된 이슈(Task) 목록을 수집합니다."""
    results = []
    try:
        # DB 연결 및 커서 생성
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        
        # 현재 시간 기준 5분 전 타임스탬프 계산 (밀리초 단위 계산)
        five_min_ago = int(time.time() * 1000) - (5 * 60 * 1000)
        
        # 신규 등록된 특정 클래스('tracker:class:Issue')의 데이터를 스캔하는 쿼리
        cur.execute("""
            SELECT
                id,
                task_data->>'identifier' AS identifier,
                task_data->>'title'      AS title,
                task_data->>'status'     AS status,
                task_data->>'priority'   AS priority,
                created_by,
                task_data->>'assignee'   AS assignee
            FROM public.tasks
            WHERE task_type = 'tracker:class:Issue'
              AND created_at > %s
            ORDER BY created_at DESC
        """, (five_min_ago,))
        rows = cur.fetchall()

        # 각 로우를 순회하며 ID 값을 사람 이름으로 치환 후 결과 배열에 저장
        for row in rows:
            _id, identifier, title, status, priority, created_by, assignee = row
            creator_name = get_person_name(cur, created_by)
            assignee_name = get_person_name(cur, assignee)
            results.append((_id, identifier, title, status, priority, creator_name, assignee_name))

        cur.close()
        conn.close()
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 데이터베이스 연결 또는 쿼리 수행 실패: {e}")
        
    return results

# ==========================================
# 4. 외부 메신저 연동 (Webhook API)
# ==========================================

def send_to_mattermost(identifier, title, status, priority, creator, assignee_name):
    """가공된 이슈 데이터를 기반으로 Mattermost에 고급 Attachment 스타일 포맷으로 알림을 전송합니다."""
    priority_label = PRIORITY_MAP.get(str(priority), "No priority")
    status_label = status.split(":")[-1] if status else "Unknown"
    assignee_mention = get_mention(assignee_name)

    # 알림창 좌측 라인에 표시될 중요도별 가시성 색상 맵 (Hex Code)
    color_map = {
        "Urgent": "#FF0000",      # 빨강
        "High": "#FF8800",        # 주황
        "Medium": "#FFCC00",      # 노랑
        "Low": "#00AA00",         # 초록
        "No priority": "#AAAAAA"  # 회색
    }
    color = color_map.get(priority_label, "#AAAAAA")

    # Mattermost 인바운드 웹훅 전송용 JSON 페이로드 규격
    payload = {
        "text": f"{assignee_mention}님, 새로운 이슈가 할당되었습니다.",
        "attachments": [
            {
                "color": color,
                "title": f"🆕 새 이슈 생성 — {identifier}",
                "text": f"**{title}**",
                "fields": [
                    {"short": True, "title": "상태", "value": status_label},
                    {"short": True, "title": "우선순위", "value": priority_label},
                    {"short": True, "title": "생성자", "value": creator},
                    {"short": True, "title": "담당자", "value": assignee_name}
                ]
            }
        ]
    }
    
    try:
        # 타임아웃 설정을 추가하여 무한 대기로 인한 스크립트 좀비화 방지
        response = requests.post(MATTERMOST_WEBHOOK, json=payload, timeout=10)
        response.raise_for_status()  # HTTP 상태 코드가 200번대가 아닐 경우 예외 발생
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Mattermost 웹훅 전송 실패: {e}")

# ==========================================
# 5. 메인 루프 (스크립트 실행 진입점)
# ==========================================

if __name__ == "__main__":
    # 1단계: 중복 알림을 필터링하기 위한 캐시 파일 정보 로드
    sent_ids = load_sent_ids()
    
    # 2단계: 최근 5분 내 생성된 데이터 스캔
    issues = get_new_issues()
    count = 0
    
    # 3단계: 조회된 데이터를 돌며 신규 데이터만 골라 알림 전송 및 메모리 적재
    for issue in issues:
        _id, identifier, title, status, priority, creator, assignee = issue
        
        # 이미 이전에 전송 완료된 고유 ID인 경우 컨티뉴 처리 (중복 알림 완전 차단)
        if _id in sent_ids:
            continue
            
        # 신규 건에 대해 알림 발송 수행
        send_to_mattermost(identifier, title, status, priority, creator, assignee)
        sent_ids.add(_id)
        count += 1
        
    # 4단계: 새로 발송된 건이 있는 경우에만 로컬 캐시 파일 저장소 업데이트
    if count > 0:
        save_sent_ids(sent_ids)
        
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {count}개의 새로운 이슈 알림 처리 완료")
