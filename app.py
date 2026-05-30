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

from flask import Flask, Response, request, jsonify, render_template
from flask_cors import CORS
import logging
import os
import json
import hashlib
import hmac
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv
from functools import wraps
from typing import Optional, Dict, Any
import re
from urllib.parse import unquote, quote

# Load environment variables
load_result = load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# IST Timezone (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now():
    """Get current time in IST"""
    return datetime.now(IST)

def get_ist_now_str():
    """Get current time in IST as ISO format string"""
    return get_ist_now().isoformat()

# 1x1 transparent GIF pixel
PIXEL_DATA = bytes([
    0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00, 0x01, 0x00, 0x80, 0x00,
    0x00, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x2C, 0x00, 0x00, 0x00, 0x00,
    0x01, 0x00, 0x01, 0x00, 0x00, 0x02, 0x02, 0x44, 0x01, 0x00, 0x3B
])

# Supabase client configuration
def get_supabase_client(use_service_role: bool = False) -> Client:
    """Get Supabase client with appropriate key"""
    url = os.environ.get("SUPABASE_URL")
    
    if use_service_role:
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        key_type = "SERVICE_ROLE"
    else:
        key = os.environ.get("SUPABASE_ANON_KEY")
        key_type = "ANON"
    
    if not url or not key:
        raise ValueError(f"SUPABASE_URL and SUPABASE_{key_type}_KEY must be set")
    
    try:
        supabase: Client = create_client(url, key)
        return supabase
    except Exception as e:
        logger.error(f"Supabase client creation error: {e}")
        raise

def detect_automated_open(user_agent: str, referer: str) -> bool:
    """Detect if the open is from an automated system"""
    automated_patterns = [
        'bot', 'crawler', 'spider', 'scanner', 'preview',
        'GoogleImageProxy', 'YahooMailProxy', 'Microsoft Office',
        'Outlook-Express', 'Thunderbird', 'AppleWebKit',
        'EmailProxy', 'LinkChecker', 'SafeBrowsing'
    ]
    
    user_agent_lower = user_agent.lower()
    referer_lower = referer.lower()
    
    for pattern in automated_patterns:
        if pattern.lower() in user_agent_lower or pattern.lower() in referer_lower:
            return True
    
    return False

# Main tracking endpoint with your URL pattern
@app.route('/track/<path:email>/<int:campaign_id>/<email_type>')
def track_email(email, campaign_id, email_type):
    """
    Tracking pixel endpoint - records email opens in IST timezone
    
    URL format: /track/{email}/{campaign_id}/{type}
    Example: /track/user@example.com/8/F2
    """
    try:
        # URL decode the email (handles @ symbol)
        email = unquote(email)
        
        # Validate email type
        valid_types = ['main', 'MAIN', 'F1', 'F2', 'F3', 'F4']
        if email_type.upper() not in [t.upper() for t in valid_types]:
            logger.warning(f"Invalid email type: {email_type}")
            return Response(PIXEL_DATA, mimetype='image/gif')
        
        # Collect tracking data
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent', 'Unknown')
        referer = request.headers.get('Referer', '')
        
        # Detect automated opens
        is_automated = detect_automated_open(user_agent, referer)
        
        # Record the open in database with IST time
        record_email_open(campaign_id, email, email_type, ip_address, user_agent, referer, is_automated)
        
        logger.info(f"Tracked open: {email} - Campaign: {campaign_id} - Type: {email_type} - Time (IST): {get_ist_now_str()}")
        
    except Exception as e:
        logger.error(f"Error tracking email open: {e}")
    
    return Response(PIXEL_DATA, mimetype='image/gif')

def record_email_open(campaign_id: int, email: str, email_type: str, ip_address: str, user_agent: str, referer: str, is_automated: bool):
    """Record email open in the Mails table with IST timezone"""
    try:
        supabase = get_supabase_client(use_service_role=True)
        
        # Get current time in IST
        current_time_ist = get_ist_now()
        current_time_str = current_time_ist.isoformat()
        
        # Check if record exists
        existing = supabase.table('Mails').select('*').eq('email', email).eq('campaign_id', campaign_id).execute()
        
        if existing.data:
            # Update existing record
            update_data = {
                'last_opened_at': current_time_str,
                'open_count': (existing.data[0].get('open_count') or 0) + 1
            }
            
            # Set first opened if not set
            if not existing.data[0].get('first_opened_at'):
                update_data['first_opened_at'] = current_time_str
            
            # Update specific fields based on email type
            if email_type.upper() == 'MAIN':
                update_data['status'] = True
                logger.info(f"Updated main email open for {email} at IST: {current_time_str}")
                
            elif email_type.upper() == 'F1':
                update_data['F1_track'] = 'Opened'
                update_data['f1_opened_at'] = current_time_str
                logger.info(f"Updated F1 followup open for {email} at IST: {current_time_str}")
                
            elif email_type.upper() == 'F2':
                update_data['F2_track'] = 'Opened'
                update_data['f2_opened_at'] = current_time_str
                logger.info(f"Updated F2 followup open for {email} at IST: {current_time_str}")
                
            elif email_type.upper() == 'F3':
                update_data['F3_track'] = 'Opened'
                update_data['f3_opened_at'] = current_time_str
                logger.info(f"Updated F3 followup open for {email} at IST: {current_time_str}")
                
            elif email_type.upper() == 'F4':
                update_data['F4_track'] = 'Opened'
                update_data['f4_opened_at'] = current_time_str
                logger.info(f"Updated F4 followup open for {email} at IST: {current_time_str}")
            
            # Update the record
            result = supabase.table('Mails').update(update_data).eq('email', email).eq('campaign_id', campaign_id).execute()
            logger.info(f"Updated record for {email} in campaign {campaign_id} - Type: {email_type}")
            
        else:
            # Create new record
            insert_data = {
                'email': email,
                'campaign_id': campaign_id,
                'open_count': 1,
                'first_opened_at': current_time_str,
                'last_opened_at': current_time_str,
                'created_at': current_time_str
            }
            
            # Set specific fields based on email type
            if email_type.upper() == 'MAIN':
                insert_data['status'] = True
                logger.info(f"Created new main email record for {email} at IST: {current_time_str}")
                
            elif email_type.upper() == 'F1':
                insert_data['F1_track'] = 'Opened'
                insert_data['f1_opened_at'] = current_time_str
                logger.info(f"Created new F1 followup record for {email} at IST: {current_time_str}")
                
            elif email_type.upper() == 'F2':
                insert_data['F2_track'] = 'Opened'
                insert_data['f2_opened_at'] = current_time_str
                logger.info(f"Created new F2 followup record for {email} at IST: {current_time_str}")
                
            elif email_type.upper() == 'F3':
                insert_data['F3_track'] = 'Opened'
                insert_data['f3_opened_at'] = current_time_str
                logger.info(f"Created new F3 followup record for {email} at IST: {current_time_str}")
                
            elif email_type.upper() == 'F4':
                insert_data['F4_track'] = 'Opened'
                insert_data['f4_opened_at'] = current_time_str
                logger.info(f"Created new F4 followup record for {email} at IST: {current_time_str}")
            
            # Insert new record
            result = supabase.table('Mails').insert(insert_data).execute()
            logger.info(f"Created new record for {email} in campaign {campaign_id} - Type: {email_type}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to record email open: {e}")
        return False




# Bulk generate tracking URLs for a campaign
@app.route('/api/tracking/bulk-generate', methods=['POST'])
def bulk_generate_tracking_urls():
    """Generate tracking URLs for multiple recipients"""
    try:
        data = request.json
        campaign_id = data.get('campaign_id')
        recipients = data.get('recipients', [])  # List of {email, name, email_type}
        
        if not campaign_id or not recipients:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        base_url = os.environ.get('BACKEND_BASE_URL', 'http://localhost:5001')
        tracking_data = []
        
        for recipient in recipients:
            email = recipient.get('email')
            email_type = recipient.get('email_type', 'MAIN')
            name = recipient.get('name', '')
            
            if not email:
                continue
            
            # URL encode the email
            encoded_email = quote(email, safe='')
            
            # Generate tracking URL for each recipient
            tracking_url = f"{base_url}/track/{encoded_email}/{campaign_id}/{email_type}"
            tracking_pixel = f'<img src="{tracking_url}" width="1" height="1" style="display:none;" />'
            
            tracking_data.append({
                'email': email,
                'name': name,
                'email_type': email_type,
                'tracking_url': tracking_url,
                'tracking_pixel': tracking_pixel
            })
        
        return jsonify({
            'success': True,
            'tracking_data': tracking_data,
            'count': len(tracking_data),
            'current_time_ist': get_ist_now_str(),
            'timezone': 'IST'
        })
        
    except Exception as e:
        logger.error(f"Error bulk generating tracking URLs: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Health check endpoint
@app.route('/health')
def health():
    """Health check endpoint with IST time"""
    return jsonify({
        'status': 'healthy',
        'timestamp_ist': get_ist_now_str(),
        'timezone': 'IST (UTC+5:30)',
        'utc_offset': '+05:30'
    })

# Dashboard endpoint
@app.route('/tracking/dashboard')
def tracking_dashboard():
    """Analytics dashboard for tracking"""
    return render_template('tracking_dashboard.html')



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
