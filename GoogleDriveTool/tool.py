import json
import gspread
import re
import os
import sys
import argparse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# --- 설정 ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "sam14_generals"  # 기본 시트 이름

def get_client(credentials_path="credentials.json", token_path="token.json"):
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token:
            token.write(creds.to_json())
    return gspread.authorize(creds)

def detect_type(value_str):
    """2번째 행의 값을 보고 타입을 결정 (int, float, str)"""
    if not value_str: return str
    try:
        int(value_str); return int
    except ValueError: pass
    try:
        float(value_str); return float
    except ValueError: pass
    return str

def get_clean_value(val, target_type):
    """값을 목표 타입으로 안전하게 변환 (에러시 0 처리)"""
    try:
        if val == "":
            return 0 if target_type in (int, float) else ""
        return target_type(val)
    except ValueError:
        return 0 if target_type in (int, float) else val

def main(sheet_name=None, output_path=None, credentials_path=None, token_path=None):
    try:
        print("구글 시트에 연결 중...")
        credentials_path = credentials_path or "credentials.json"
        token_path = token_path or "token.json"
        gc = get_client(credentials_path, token_path)
        sheet_name = sheet_name or SHEET_NAME
        
        # output_path가 디렉토리면 {path}/{sheet_name}.json, 아니면 그대로 사용
        if output_path:
            if os.path.isdir(output_path):
                json_file_name = os.path.join(output_path, f"{sheet_name}.json")
            else:
                json_file_name = output_path
        else:
            json_file_name = f"{sheet_name}.json"

        # 에러 발생 시 open_by_url 사용 고려
        sh = gc.open(sheet_name)
        worksheet = sh.get_worksheet(0)
        
        raw_data = worksheet.get_all_values()
        if len(raw_data) < 2:
            print("데이터가 너무 적습니다. (헤더 + 데이터 필요)")
            return

        headers = raw_data[0]
        type_row = raw_data[1]
        
        # 1. 컬럼 타입 감지
        column_types = [detect_type(val) for val in type_row]
        
        # 2. 헤더 그룹화 (필터링 로직 추가됨)
        header_map = {}
        regex = re.compile(r'^(.*?)[ _]*(\d+)$') 

        for idx, header in enumerate(headers):
            header = header.strip()
            
            # [신규 규칙 1] 헤더가 비어있거나 '#'으로 시작하면 무시 (주석 컬럼)
            if not header or header.startswith('#'):
                continue

            match = regex.match(header)
            if match:
                base_name = match.group(1).strip()
                if base_name == "": base_name = header 
            else:
                base_name = header
            
            if base_name not in header_map:
                header_map[base_name] = []
            header_map[base_name].append(idx)

        final_data = []

        # 3. 데이터 변환
        for row in raw_data[1:]:
            
            # [신규 규칙 2] 첫 번째 컬럼(인덱스)이 비어있으면 유효하지 않은 행으로 간주하고 건너뜀
            if not row or not row[0].strip():
                continue

            item = {}
            for base_name, col_indices in header_map.items():
                
                # 배열 여부 판단
                first_col_idx = col_indices[0]
                is_array = len(col_indices) > 1 or headers[first_col_idx].strip() != base_name
                
                if is_array:
                    arr = []
                    for col_idx in col_indices:
                        if col_idx < len(row):
                            val = row[col_idx]
                            type_ = column_types[col_idx]
                            clean_val = get_clean_value(val, type_)
                            
                            if clean_val != "":
                                arr.append(clean_val)
                    item[base_name] = arr
                else:
                    if first_col_idx < len(row):
                        val = row[first_col_idx]
                        type_ = column_types[first_col_idx]
                        item[base_name] = get_clean_value(val, type_)
            
            final_data.append(item)

        # 4. JSON 파일 덮어쓰기
        try:
            with open(json_file_name, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=4)
            
            abs_path = os.path.abspath(json_file_name)
            print(f"✅ 성공! 파일이 저장되었습니다.")
            print(f"   위치: {abs_path}")
            print(f"   데이터: {len(final_data)}개")
            
        except PermissionError:
            print(f"❌ 오류: '{json_file_name}' 파일을 저장할 수 없습니다.")
            print("파일이 다른 프로그램에서 열려 있다면 닫고 다시 실행해주세요.")

    except Exception as e:
        print(f"❌ 예상치 못한 오류 발생: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Export Google Sheet to JSON')
    parser.add_argument('-s', '--sheet', help='Sheet name (overrides default)', default=None)
    parser.add_argument('-o', '--output', help='Output file path (default: <sheet_name>.json)', default=None)
    parser.add_argument('-c', '--credentials', help='Path to credentials.json file', default=None)
    parser.add_argument('-t', '--token', help='Path to token.json file', default=None)
    args = parser.parse_args()
    main(args.sheet, args.output, args.credentials, args.token)