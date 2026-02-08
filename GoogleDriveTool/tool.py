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
DEFAULT_SHEET_NAME = "sam_data_integrated"  # 기본 파일(Workbook) 이름

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

def process_worksheet(worksheet, output_dir):
    """단일 워크시트를 처리하여 JSON으로 저장하는 함수"""
    ws_title = worksheet.title
    
    # [규칙] 워크시트 이름이 '#'으로 시작하면 스킵
    if ws_title.startswith('#'):
        print(f"⏭️  Skip: '{ws_title}' (주석용 시트)")
        return

    print(f"🔄 Processing: '{ws_title}'...")
    
    raw_data = worksheet.get_all_values()
    if len(raw_data) < 2:
        print(f"⚠️  Warning: '{ws_title}' 데이터가 너무 적습니다. (Skip)")
        return

    headers = raw_data[0]
    type_row = raw_data[1]
    
    # 1. 컬럼 타입 감지
    column_types = [detect_type(val) for val in type_row]
    
    # 2. 헤더 그룹화
    header_map = {}
    regex = re.compile(r'^(.*?)[ _]*(\d+)$') 

    for idx, header in enumerate(headers):
        header = header.strip()
        
        # 헤더가 비어있거나 '#'으로 시작하면 무시
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
        # 첫 번째 컬럼(ID)이 비어있으면 유효하지 않은 행으로 간주
        if not row or not row[0].strip():
            continue

        item = {}
        for base_name, col_indices in header_map.items():
            
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

    # 4. JSON 파일 저장
    json_filename = f"{ws_title}.json"
    
    # [수정된 부분] 변수명을 output_dir로 통일
    if output_dir:
         file_path = os.path.join(output_dir, json_filename)
    else:
         file_path = json_filename

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, ensure_ascii=False, indent=4)
        print(f"✅ Saved: {file_path} ({len(final_data)} items)")
        
    except PermissionError:
        print(f"❌ Error: '{file_path}' 파일을 저장할 수 없습니다. (Permission Denied)")
    except Exception as e:
        print(f"❌ Error saving '{file_path}': {e}")


def main(sheet_name=None, output_dir=None, credentials_path=None, token_path=None):
    try:
        credentials_path = credentials_path or "credentials.json"
        token_path = token_path or "token.json"
        
        print("connecting to Google Sheets...")
        gc = get_client(credentials_path, token_path)
        
        target_sheet_name = sheet_name or DEFAULT_SHEET_NAME
        
        # 워크북(파일) 열기
        try:
            sh = gc.open(target_sheet_name)
        except gspread.exceptions.SpreadsheetNotFound:
            print(f"❌ Error: 스프레드시트 '{target_sheet_name}'를 찾을 수 없습니다.")
            return

        print(f"📂 Workbook: '{sh.title}'")

        # 출력 폴더 생성 (없으면 생성)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"📁 Created directory: {output_dir}")

        # 모든 워크시트 순회
        worksheets = sh.worksheets()
        print(f"📊 Found {len(worksheets)} worksheets.")
        print("-" * 30)

        for ws in worksheets:
            process_worksheet(ws, output_dir)

        print("-" * 30)
        print("🎉 All done.")

    except Exception as e:
        print(f"❌ Unexpected Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Export Google Sheet Worksheets to JSON files')
    parser.add_argument('-s', '--sheet', help='Google Sheet Name (Workbook)', default=None)
    parser.add_argument('-o', '--output', help='Output Directory (default: current dir)', default=None)
    parser.add_argument('-c', '--credentials', help='Path to credentials.json', default=None)
    parser.add_argument('-t', '--token', help='Path to token.json', default=None)
    
    args = parser.parse_args()
    
    main(args.sheet, args.output, args.credentials, args.token)