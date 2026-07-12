"""
Strava OAuth Authorization
Run this once to get your access token and refresh token.
"""

import os
import webbrowser
from stravalib.client import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

STRAVA_CLIENT_ID = os.getenv('STRAVA_CLIENT_ID')
STRAVA_CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET')

def authorize_strava():
    """
    Step-by-step OAuth flow to get Strava access token.
    """
    print("\n" + "="*70)
    print("STRAVA OAUTH AUTHORIZATION")
    print("="*70 + "\n")
    
    if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET:
        print("❌ Error: STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET must be set in .env")
        return
    
    client = Client()
    
    # Step 1: Generate authorization URL
    authorize_url = client.authorization_url(
        client_id=STRAVA_CLIENT_ID,
        redirect_uri='http://localhost',
        scope=['activity:write', 'activity:read_all']
    )
    
    print("Step 1: Authorize the app")
    print("-" * 70)
    print(f"\nOpening browser to authorize Training Hub with Strava...")
    print(f"\nIf browser doesn't open, go to this URL:\n{authorize_url}\n")
    
    # Open browser
    webbrowser.open(authorize_url)
    
    # Step 2: User authorizes and gets redirected
    print("\nStep 2: After authorizing, you'll be redirected to a URL like:")
    print("  http://localhost/?state=&code=XXXXXXXXXXXXXX&scope=read,activity:write,activity:read_all")
    print("\nCopy the ENTIRE URL from your browser's address bar.")
    
    redirect_response = input("\nPaste the full redirect URL here: ").strip()
    
    # Step 3: Extract code from URL
    if '?code=' in redirect_response or '&code=' in redirect_response:
        # Parse code from URL
        code = redirect_response.split('code=')[1].split('&')[0]
    else:
        print("\n❌ Error: Could not find 'code=' in the URL. Make sure you pasted the full URL.")
        return
    
    print(f"\n✅ Authorization code received: {code[:10]}...")
    
    # Step 4: Exchange code for access token
    print("\nStep 3: Exchanging authorization code for access token...")
    
    try:
        token_response = client.exchange_code_for_token(
            client_id=STRAVA_CLIENT_ID,
            client_secret=STRAVA_CLIENT_SECRET,
            code=code
        )
        
        access_token = token_response['access_token']
        refresh_token = token_response['refresh_token']
        expires_at = token_response['expires_at']
        
        print("\n✅ Success! Tokens received:")
        print(f"   Access Token:  {access_token[:20]}...")
        print(f"   Refresh Token: {refresh_token[:20]}...")
        print(f"   Expires At:    {expires_at}")
        
        # Step 5: Save tokens to .env
        print("\n" + "="*70)
        print("SAVING TOKENS TO .ENV")
        print("="*70 + "\n")
        
        # Read current .env
        env_path = '.env'
        with open(env_path, 'r') as f:
            env_content = f.read()
        
        # Check if tokens already exist
        if 'STRAVA_ACCESS_TOKEN' in env_content:
            # Update existing tokens
            lines = env_content.split('\n')
            new_lines = []
            for line in lines:
                if line.startswith('STRAVA_ACCESS_TOKEN='):
                    new_lines.append(f'STRAVA_ACCESS_TOKEN={access_token}')
                elif line.startswith('STRAVA_REFRESH_TOKEN='):
                    new_lines.append(f'STRAVA_REFRESH_TOKEN={refresh_token}')
                elif line.startswith('STRAVA_EXPIRES_AT='):
                    new_lines.append(f'STRAVA_EXPIRES_AT={expires_at}')
                else:
                    new_lines.append(line)
            env_content = '\n'.join(new_lines)
        else:
            # Add new tokens
            env_content += f'\n\n# Strava OAuth Tokens\n'
            env_content += f'STRAVA_ACCESS_TOKEN={access_token}\n'
            env_content += f'STRAVA_REFRESH_TOKEN={refresh_token}\n'
            env_content += f'STRAVA_EXPIRES_AT={expires_at}\n'
        
        # Write back to .env
        with open(env_path, 'w') as f:
            f.write(env_content)
        
        print("✅ Tokens saved to .env file")
        print("\nYou can now use the Strava API!")
        print("Run the publish script to upload workouts to Strava.")
        
    except Exception as e:
        print(f"\n❌ Error exchanging code for token: {e}")
        print("\nMake sure:")
        print("  1. Your Client ID and Secret are correct in .env")
        print("  2. You authorized the app within the last few minutes")
        print("  3. You pasted the FULL redirect URL")


if __name__ == '__main__':
    authorize_strava()
