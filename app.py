# Copyright (c) 2024 The Project Contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
from flask import Flask, Response, request, render_template
import logging
import os
import json
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_result = load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# Test dotenv loading
def test_dotenv_loading():
    """Test if .env file is loaded successfully"""
    logging.info("=" * 50)
    logging.info("TESTING DOTENV LOADING")
    logging.info("=" * 50)
    
    # Check if .env file exists
    env_file_path = os.path.join(os.getcwd(), '.env')
    env_exists = os.path.exists(env_file_path)
    logging.info(f"📁 .env file exists: {env_exists}")
    logging.info(f"📁 .env file path: {env_file_path}")
    
    # Check load_dotenv result
    logging.info(f"📥 load_dotenv() result: {load_result}")
    
    # Check environment variables
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_ANON_KEY")
    
    logging.info(f"🔗 SUPABASE_URL loaded: {'✅ YES' if supabase_url else '❌ NO'}")
    if supabase_url:
        logging.info(f"🔗 SUPABASE_URL value: {supabase_url[:30]}...")
    else:
        logging.info("🔗 SUPABASE_URL value: None")
    
    logging.info(f"🔑 SUPABASE_ANON_KEY loaded: {'✅ YES' if supabase_key else '❌ NO'}")
    if supabase_key:
        logging.info(f"🔑 SUPABASE_ANON_KEY value: {supabase_key[:20]}...")
    else:
        logging.info("🔑 SUPABASE_ANON_KEY value: None")
    
    # Check all environment variables starting with SUPABASE
    supabase_vars = {k: v for k, v in os.environ.items() if k.startswith('SUPABASE')}
    logging.info(f"📋 All SUPABASE environment variables: {list(supabase_vars.keys())}")
    
    logging.info("=" * 50)
    
    return supabase_url and supabase_key

# Run the test
test_dotenv_loading()

# Supabase client configuration
def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY environment variables must be set. Please check your .env file.")
    
    try:
        supabase: Client = create_client(url, key)
        return supabase
    except Exception as e:
        logging.error(f"Supabase client creation error: {e}")
        raise

# Check if Mails table is accessible
def initialize_database():
    try:
        supabase = get_supabase_client()
        
        # Check if Mails table exists by trying to query it
        result = supabase.table('Mails').select('email').limit(1).execute()
        logging.info("Database table 'Mails' exists and is accessible")
        
    except Exception as e:
        logging.warning(f"Table 'Mails' may not exist or be accessible: {e}")
        logging.info("Please ensure your Supabase Mails table has the following columns:")
        logging.info("- email")
        logging.info("- campaign_id") 
        logging.info("- status")
        logging.info("- open_count (optional)")
        logging.info("- first_opened_at (optional)")
        logging.info("- last_opened_at (optional)")

app = Flask(__name__)
pixel_data = (
    b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00'
    b'\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x4c\x01\x00\x3b'
)
@app.route('/track/<email>/<campaign_id>')
def track_email(email, campaign_id):
    try:
        ip_address = request.remote_addr
        
        # Store open event in Supabase Mails table
        supabase = get_supabase_client()
        
        # First, try to get existing record by email and campaign_id
        existing = supabase.table('Mails').select('*').eq('email', email).eq('campaign_id', campaign_id).execute()
        
        if existing.data:
            # Update existing record - only update last_opened_at, keep first_opened_at unchanged
            # Double-check that we found the exact match for email AND campaign_id
            matched_record = existing.data[0]
            if matched_record.get('email') == email and matched_record.get('campaign_id') == campaign_id:
                current_count = matched_record.get('open_count', 0)
                
                result = supabase.table('Mails').update({
                    'status': True,
                    'open_count': current_count + 1,
                    'last_opened_at': datetime.now().isoformat()  # Only update last opened time
                }).eq('email', email).eq('campaign_id', campaign_id).execute()
                
                logging.info(f"Updated existing record for email: {email}, campaign: {campaign_id}")
            else:
                logging.warning(f"Record found but email/campaign_id mismatch for: {email}, {campaign_id}")
            
        else:
            # Insert new record - set both first and last opened times to current time
            current_time = datetime.now().isoformat()
            result = supabase.table('Mails').insert({
                'email': email,
                'campaign_id': campaign_id,
                'status': True,
                'open_count': 1,
                'first_opened_at': current_time,  # Set first opened time
                'last_opened_at': current_time,   # Set last opened time (same as first for first open)
            }).execute()
            
            logging.info(f"Created new record for email: {email}, campaign: {campaign_id}")
        
        logging.info(f"Email open tracked for email: {email}, campaign: {campaign_id}")

    except Exception as e:
        logging.error(f"Error logging email open: {e}")
    return Response(pixel_data, mimetype='image/gif')

@app.route('/test-env')
def test_environment():
    """Test endpoint to check environment variables"""
    try:
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_ANON_KEY")
        
        env_file_path = os.path.join(os.getcwd(), '.env')
        env_exists = os.path.exists(env_file_path)
        
        result = {
            "env_file_exists": env_exists,
            "env_file_path": env_file_path,
            "load_dotenv_result": load_result,
            "supabase_url_loaded": bool(supabase_url),
            "supabase_url_value": supabase_url[:30] + "..." if supabase_url else None,
            "supabase_key_loaded": bool(supabase_key),
            "supabase_key_value": supabase_key[:20] + "..." if supabase_key else None,
            "all_supabase_vars": list({k: v for k, v in os.environ.items() if k.startswith('SUPABASE')}.keys())
        }
        
        return f"""
        <h1>Environment Variables Test</h1>
        <pre>{json.dumps(result, indent=2)}</pre>
        <p><a href="/dashboard">Go to Dashboard</a></p>
        """
    except Exception as e:
        return f"Error: {e}"

@app.route('/dashboard2')
def show_dashboard2():
    """Enhanced dashboard with tracking pixel integration"""
    try:
        # Fetch latest opens from Mails table
        supabase = get_supabase_client()
        
        result = supabase.table('Mails').select(
            'email, campaign_id, status, open_count, first_opened_at, last_opened_at, ip_address'
        ).order('last_opened_at', desc=True).limit(500).execute()
        
        records = result.data
        headers = ['email', 'campaign_id', 'status', 'open_count', 'first_opened', 'last_opened', 'ip_address']
        
        def fmt(ts):
            if ts:
                try:
                    # Parse ISO format timestamp and format it
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    return str(ts)
            return ''
        
        rows = [[
            r.get('email', ''),
            r.get('campaign_id', ''),
            r.get('status', ''),
            r.get('open_count', 0),
            fmt(r.get('first_opened_at')),
            fmt(r.get('last_opened_at')),
            r.get('ip_address', '')
        ] for r in records]
        
        sheet_name_display = "Supabase: Mails Table"

        return render_template('dashboard2.html', headers=headers, rows=rows, sheet_name=sheet_name_display)
    except Exception as e:
        return render_template('dashboard2.html', error=f"Could not retrieve data: {e}")

@app.route('/dashboard')
def show_dashboard():
    try:
        # Fetch latest opens from Mails table
        supabase = get_supabase_client()
        
        result = supabase.table('Mails').select(
            'email, campaign_id, status, open_count, first_opened_at, last_opened_at, ip_address'
        ).order('last_opened_at', desc=True).limit(500).execute()
        
        records = result.data
        headers = ['email', 'campaign_id', 'status', 'open_count', 'first_opened', 'last_opened', 'ip_address']
        
        def fmt(ts):
            if ts:
                try:
                    # Parse ISO format timestamp and format it
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    return str(ts)
            return ''
        
        rows = [[
            r.get('email', ''),
            r.get('campaign_id', ''),
            r.get('status', ''),
            r.get('open_count', 0),
            fmt(r.get('first_opened_at')),
            fmt(r.get('last_opened_at')),
            r.get('ip_address', '')
        ] for r in records]
        
        sheet_name_display = "Supabase: Mails Table"

        return render_template('dashboard.html', headers=headers, rows=rows, sheet_name=sheet_name_display)
    except Exception as e:
        return render_template('dashboard.html', error=f"Could not retrieve data: {e}")

if __name__ == '__main__':
    initialize_database()
    app.run(host='0.0.0.0', port=5001, debug=True)