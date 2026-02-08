import json
import gspread
import os
import sys
import argparse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# --- 설정 ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
DEFAULT_SHEET_NAME = "sam_string"  # 기본 파일 이름

# [중요] 처리할 언어 코드 목록 (여기에 없으면 무시됨)
TARGET_LANGUAGES = ["en", "ko", "ja", "zh-Hans", "zh-Hant"]

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

def save_i18n_json(base_output_dir, lang_code, sheet_name, data):
    """ output/lang_code/sheet_name.json 형태로 저장 """
    
    # 1. 언어 폴더 경로 생성 (예: ./output/ko)
    if base_output_dir:
        target_dir = os.path.join(base_output_dir, lang_code)
    else:
        target_dir = lang_code 
        
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        
    # 2. 파일 경로 생성
    file_path = os.path.join(target_dir, f"{sheet_name}.json")
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"   ✅ Saved [{lang_code}]: {file_path} ({len(data)} keys)")
        
    except PermissionError:
        print(f"   ❌ Error: '{file_path}' 권한 없음. 파일을 닫아주세요.")
    except Exception as e:
        print(f"   ❌ Error saving '{file_path}': {e}")

def process_worksheet(worksheet, output_dir):
    """다국어 시트를 처리하여 언어별 폴더에 Key-Value JSON으로 저장"""
    ws_title = worksheet.title
    
    # 1. 워크시트 스킵 조건
    if ws_title.startswith('#'):
        print(f"⏭️  Skip: '{ws_title}' (주석용 시트)")
        return

    print(f"🔄 Processing: '{ws_title}'...")
    
    raw_data = worksheet.get_all_values()
    if len(raw_data) < 2:
        print(f"⚠️  Warning: '{ws_title}' 데이터가 너무 적습니다. (Skip)")
        return

    headers = raw_data[0]
    
    processed_count = 0

    # 헤더(컬럼)를 순회하며 지정된 언어인지 확인
    for col_idx, header in enumerate(headers):
        
        # 0번 컬럼(Key)은 건너뜀
        if col_idx == 0:
            continue
            
        lang_code = header.strip()
        
        # [핵심 변경] 지정된 언어 코드가 아니면 무시 (whitelist 방식)
        if lang_code not in TARGET_LANGUAGES:
            # 필요하다면 로그 출력: print(f"   ℹ️ Ignored column: {lang_code}")
            continue
            
        # 해당 언어의 Key-Value 데이터 생성
        i18n_data = {}
        
        for row in raw_data[1:]:
            if not row: continue
            
            key = row[0].strip()
            
            # Key가 없거나 '#'으로 시작하면 해당 행은 무시 (주석)
            if not key or key.startswith('#'):
                continue
                
            # 값 가져오기
            if col_idx < len(row):
                val = row[col_idx]
            else:
                val = ""
            
            i18n_data[key] = val

        # 저장
        save_i18n_json(output_dir, lang_code, ws_title, i18n_data)
        processed_count += 1
    
    if processed_count == 0:
        print(f"   ⚠️  No valid language columns found in '{ws_title}'.")


def main(sheet_name=None, output_dir=None, credentials_path=None, token_path=None):
    try:
        credentials_path = credentials_path or "credentials.json"
        token_path = token_path or "token.json"
        
        print(f"Target Languages: {TARGET_LANGUAGES}")
        print("connecting to Google Sheets (i18n Mode)...")
        
        gc = get_client(credentials_path, token_path)
        
        target_sheet_name = sheet_name or DEFAULT_SHEET_NAME
        
        try:
            sh = gc.open(target_sheet_name)
        except gspread.exceptions.SpreadsheetNotFound:
            print(f"❌ Error: 스프레드시트 '{target_sheet_name}'를 찾을 수 없습니다.")
            return

        print(f"📂 Workbook: '{sh.title}'")

        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

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
    parser = argparse.ArgumentParser(description='Export Google Sheet for i18n (Key-Value by Language)')
    parser.add_argument('-s', '--sheet', help='Google Sheet Name (Workbook)', default=None)
    parser.add_argument('-o', '--output', help='Output Root Directory', default=None)
    parser.add_argument('-c', '--credentials', help='Path to credentials.json', default=None)
    parser.add_argument('-t', '--token', help='Path to token.json', default=None)
    
    args = parser.parse_args()
    
    main(args.sheet, args.output, args.credentials, args.token)