#!/usr/bin/env python3
"""
GitHub Copilot PR 리뷰 요청 스크립트
공식 MCP 서버를 사용해서 Copilot 리뷰 요청
"""
import os
import json
import subprocess
import sys
import argparse
import time

def get_pull_request_info():
    """GitHub Actions 컨텍스트에서 PR 정보 가져오기"""
    # 환경변수에서 가져오기
    repository = os.environ.get('GITHUB_REPOSITORY', '')
    if not repository:
        print("❌ GITHUB_REPOSITORY 환경변수가 없습니다.")
        return None, None, None
    
    owner, repo = repository.split('/')
    
    # PR 번호는 여러 방법으로 가져올 수 있음
    pr_number = None
    
    # 1. 환경변수에서 직접 가져오기 (workflow_dispatch 등)
    pr_number = os.environ.get('PR_NUMBER')
    
    # 2. GitHub event에서 가져오기
    if not pr_number:
        github_event_path = os.environ.get('GITHUB_EVENT_PATH')
        if github_event_path and os.path.exists(github_event_path):
            with open(github_event_path, 'r') as f:
                event_data = json.load(f)
                
            # pull_request 이벤트인 경우
            if 'pull_request' in event_data:
                pr_number = event_data['pull_request']['number']
            # issue_comment 이벤트에서 PR 댓글인 경우
            elif 'issue' in event_data and 'pull_request' in event_data['issue']:
                pr_number = event_data['issue']['number']
    
    if not pr_number:
        print("❌ PR 번호를 찾을 수 없습니다.")
        return None, None, None
    
    return owner, repo, int(pr_number)

def setup_mcp_server():
    """MCP 서버 경로 확인 - 재사용 가능한 워크플로우용"""
    print("🔧 GitHub MCP 서버 확인 중...")
    
    # 현재 워킹 디렉토리에서 MCP 서버 찾기
    # 재사용 가능한 워크플로우에서는 현재 디렉토리에 다운로드됨
    server_path = os.path.join(os.getcwd(), 'github-mcp-server')
    
    if os.path.exists(server_path):
        print(f"✅ MCP 서버 확인됨: {server_path}")
        return server_path
    else:
        print(f"❌ MCP 서버를 찾을 수 없습니다: {server_path}")
        print("   GitHub Actions workflow에서 MCP 서버가 먼저 다운로드되어야 합니다.")
        return None

def request_copilot_review(owner, repo, pull_number):
    """GitHub 공식 MCP 서버를 통해 Copilot 리뷰 요청"""
    
    print(f"=== Copilot 리뷰 요청: {owner}/{repo}#{pull_number} ===")
    
    # GitHub 토큰 확인
    github_token = os.environ.get('GITHUB_TOKEN')
    if not github_token:
        print("❌ GITHUB_TOKEN 환경변수가 설정되지 않았습니다.")
        return False
    
    # MCP 서버 설정
    server_path = setup_mcp_server()
    if not server_path:
        print("❌ MCP 서버 설정 실패")
        return False
    
    process = None
    try:
        # 환경변수 설정
        env = os.environ.copy()
        env['GITHUB_PERSONAL_ACCESS_TOKEN'] = github_token
        
        # MCP 서버 시작
        print("🚀 MCP 서버 시작...")
        process = subprocess.Popen(
            [server_path, "stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            bufsize=0
        )
        
        # 초기화 요청
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {
                        "listChanged": True
                    },
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "github-actions-client",
                    "version": "1.0.0"
                }
            }
        }
        
        print("📡 초기화 요청 전송...")
        process.stdin.write(json.dumps(init_request) + '\n')
        process.stdin.flush()
        
        # 초기화 응답 읽기
        init_response = process.stdout.readline()
        print(f"✅ 초기화 완료: {init_response.strip()[:100]}...")
        
        # Copilot 리뷰 요청
        review_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "request_copilot_review",
                "arguments": {
                    "owner": owner,
                    "repo": repo,
                    "pullNumber": int(pull_number)
                }
            }
        }
        
        print(f"🤖 Copilot 리뷰 요청 전송...")
        print(f"   Repository: {owner}/{repo}")
        print(f"   Pull Request: #{pull_number}")
        
        process.stdin.write(json.dumps(review_request) + '\n')
        process.stdin.flush()
        
        # 응답 대기 (최대 30초)
        print("⏳ Copilot 응답 대기 중...")
        
        start_time = time.time()
        while time.time() - start_time < 30:
            if process.stdout.readable():
                response = process.stdout.readline()
                if response:
                    print(f"📥 응답 수신: {response.strip()}")
                    
                    try:
                        response_data = json.loads(response)
                        
                        if 'error' in response_data:
                            error = response_data['error']
                            print(f"❌ 오류 발생:")
                            print(f"   코드: {error.get('code', 'unknown')}")
                            print(f"   메시지: {error.get('message', 'unknown error')}")
                            return False
                            
                        elif 'result' in response_data:
                            result = response_data['result']
                            print(f"✅ Copilot 리뷰 요청 성공!")
                            print(f"   결과: {result}")
                            return True
                            
                        else:
                            print(f"🔍 예상치 못한 응답: {response_data}")
                            
                    except json.JSONDecodeError as e:
                        print(f"⚠️ JSON 파싱 오류: {e}")
                        print(f"   원본 응답: {response}")
                        
                    break
            
            time.sleep(0.1)
        
        print("⏰ 응답 시간 초과 (30초)")
        return False
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return False
        
    finally:
        # 프로세스 정리
        if process:
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                process.kill()
                
    return False

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='GitHub Copilot 리뷰 요청')
    parser.add_argument('--owner', help='Repository owner')
    parser.add_argument('--repo', help='Repository name') 
    parser.add_argument('--pr', help='Pull request number')
    
    args = parser.parse_args()
    
    # 인자로 받지 않은 경우 GitHub Actions 환경에서 가져오기
    if args.owner and args.repo and args.pr:
        owner, repo, pull_number = args.owner, args.repo, int(args.pr)
    else:
        owner, repo, pull_number = get_pull_request_info()
        if not owner or not repo or not pull_number:
            print("❌ PR 정보를 가져올 수 없습니다.")
            sys.exit(1)
    
    print(f"🚀 GitHub Copilot 리뷰 요청 시작")
    print(f"📋 타겟: {owner}/{repo}#{pull_number}")
    
    success = request_copilot_review(owner, repo, pull_number)
    
    if success:
        print("\n🎉 Copilot 리뷰 요청이 성공적으로 완료되었습니다!")
        sys.exit(0)
    else:
        print("\n❌ Copilot 리뷰 요청이 실패했습니다.")
        sys.exit(1)

if __name__ == "__main__":
    main()
