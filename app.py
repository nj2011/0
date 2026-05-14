from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from datetime import datetime
import hashlib
import re
from collections import defaultdict

app = Flask(__name__)
CORS(app)

# Database file path
DB_FILE = 'database.json'
CHECK_CACHE = {}  # Simple in-memory cache for check results

def load_database():
    """Load database from file"""
    if not os.path.exists(DB_FILE):
        return {
            "combos": [],
            "hashes": [],
            "email_index": {},  # email -> list of passwords
            "username_index": {},  # username -> list of combos
            "metadata": {
                "total_lines": 0,
                "latest_added": 0,
                "date_added": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "added_by": "System"
            }
        }
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Ensure indexes exist for backward compatibility
            if 'email_index' not in data:
                data['email_index'] = {}
            if 'username_index' not in data:
                data['username_index'] = {}
            return data
    except Exception as e:
        print(f"Error loading database: {e}")
        return {
            "combos": [],
            "hashes": [],
            "email_index": {},
            "username_index": {},
            "metadata": {
                "total_lines": 0,
                "latest_added": 0,
                "date_added": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "added_by": "System"
            }
        }

def save_database(data):
    """Save database to file"""
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving database: {e}")
        return False

def hash_combo(combo):
    """Create MD5 hash of combo for faster lookup"""
    return hashlib.md5(combo.strip().lower().encode()).hexdigest()

def extract_email(combo):
    """Extract email from combo"""
    if ':' in combo:
        email_part = combo.split(':')[0]
        if '@' in email_part:
            return email_part.lower()
    return None

def extract_username(combo):
    """Extract username from combo"""
    if ':' in combo:
        username_part = combo.split(':')[0]
        if '@' not in username_part:
            return username_part.lower()
    return None

def update_indexes(db, combo):
    """Update email and username indexes"""
    # Update email index
    email = extract_email(combo)
    if email:
        if email not in db['email_index']:
            db['email_index'][email] = []
        password = combo.split(':', 1)[1] if ':' in combo else ''
        if password not in db['email_index'][email]:
            db['email_index'][email].append(password)
    
    # Update username index
    username = extract_username(combo)
    if username:
        if username not in db['username_index']:
            db['username_index'][username] = []
        if combo not in db['username_index'][username]:
            db['username_index'][username].append(combo)

@app.route('/', methods=['GET', 'POST', 'OPTIONS'])
def handle_request():
    """Main endpoint for database operations"""
    if request.method == 'OPTIONS':
        return '', 200
    
    if request.method == 'GET':
        action = request.args.get('action')
        
        if action == 'metadata':
            db = load_database()
            return jsonify(db.get('metadata', {}))
        
        elif action == 'stats':
            db = load_database()
            return jsonify({
                'total_combos': len(db.get('combos', [])),
                'unique_hashes': len(db.get('hashes', [])),
                'unique_emails': len(db.get('email_index', {})),
                'unique_usernames': len(db.get('username_index', {})),
                'metadata': db.get('metadata', {})
            })
        
        return jsonify({
            "status": "ok",
            "message": "Database server running",
            "endpoints": {
                "GET ?action=metadata": "Get database metadata",
                "GET ?action=stats": "Get detailed statistics",
                "POST /check_combo": "Check if combo exists",
                "POST /check_email": "Check email and get passwords",
                "POST /check_username": "Check username",
                "POST /add_bulk_public": "Add combos (no auth)"
            }
        })
    
    elif request.method == 'POST':
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        
        if 'combos' in data:
            combos_text = data['combos']
            combos = [c.strip() for c in combos_text.split('\n') if c.strip() and ':' in c]
            
            if not combos:
                return jsonify({
                    'success': False,
                    'error': 'No valid combos found in input'
                }), 400
            
            db = load_database()
            existing_hashes = set(db.get('hashes', []))
            
            matched = []
            non_matched = []
            
            for combo in combos:
                combo_hash = hash_combo(combo)
                if combo_hash in existing_hashes:
                    matched.append(combo)
                else:
                    non_matched.append(combo)
            
            return jsonify({
                'success': True,
                'total_checked': len(combos),
                'matches': len(matched),
                'non_matches': len(non_matched),
                'non_matched_combos': non_matched
            })
        
        return jsonify({
            'success': False,
            'error': 'Invalid request. Use "combos" parameter'
        }), 400

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    db = load_database()
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "database_exists": os.path.exists(DB_FILE),
        "total_combos": len(db.get('combos', []))
    })

@app.route('/add_bulk_public', methods=['POST', 'OPTIONS'])
def add_bulk_public():
    """Public endpoint for auto-uploading valid accounts"""
    if request.method == 'OPTIONS':
        return '', 200
    
    if not request.is_json:
        return jsonify({'success': False, 'error': 'JSON required'}), 400
    
    data = request.get_json()
    combos_text = data.get('combos', '')
    added_by = data.get('added_by', 'Auto-Upload')
    
    if not combos_text:
        return jsonify({'success': False, 'error': 'No combos provided'}), 400
    
    # Split and validate combos
    lines = combos_text.split('\n')
    combos = []
    for line in lines:
        line = line.strip()
        if line and ':' in line:
            # Validate format (has at least one colon and both sides have content)
            parts = line.split(':', 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                combos.append(line)
    
    if not combos:
        return jsonify({'success': False, 'error': 'No valid combos found'}), 400
    
    db = load_database()
    existing_hashes = set(db.get('hashes', []))
    
    added = 0
    skipped = 0
    failed = 0
    added_combos = []
    
    for combo in combos:
        combo_hash = hash_combo(combo)
        if combo_hash not in existing_hashes:
            existing_hashes.add(combo_hash)
            if 'combos' not in db:
                db['combos'] = []
            if 'hashes' not in db:
                db['hashes'] = []
            db['combos'].append(combo)
            db['hashes'].append(combo_hash)
            
            # Update indexes
            if 'email_index' not in db:
                db['email_index'] = {}
            if 'username_index' not in db:
                db['username_index'] = {}
            update_indexes(db, combo)
            
            added += 1
            if len(added_combos) < 5:
                added_combos.append(combo)
        else:
            skipped += 1
    
    db['metadata'] = {
        'total_lines': len(db['combos']),
        'latest_added': added,
        'date_added': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'added_by': added_by
    }
    
    if save_database(db):
        return jsonify({
            'success': True,
            'added': added,
            'skipped': skipped,
            'failed': 0,
            'total': len(db['combos']),
            'sample_added': added_combos
        })
    else:
        return jsonify({'success': False, 'error': 'Failed to save database'}), 500

@app.route('/check_combo', methods=['POST', 'OPTIONS'])
def check_combo():
    """Check if a specific combo exists in the database"""
    if request.method == 'OPTIONS':
        return '', 200
    
    if not request.is_json:
        return jsonify({'exists': False, 'error': 'JSON required'}), 400
    
    data = request.get_json()
    combo = data.get('combo', '').strip().lower()
    
    if not combo or ':' not in combo:
        return jsonify({'exists': False, 'error': 'Invalid combo format'}), 400
    
    db = load_database()
    combo_hash = hash_combo(combo)
    existing_hashes = set(db.get('hashes', []))
    
    if combo_hash in existing_hashes:
        # Find the combo in database to get metadata
        combos_list = db.get('combos', [])
        found_combo = None
        for c in combos_list:
            if hash_combo(c) == combo_hash:
                found_combo = c
                break
        
        return jsonify({
            'exists': True,
            'data': {
                'combo': combo,
                'added_date': db.get('metadata', {}).get('date_added', 'Unknown'),
                'added_by': db.get('metadata', {}).get('added_by', 'Unknown')
            }
        })
    else:
        return jsonify({'exists': False, 'data': None})

@app.route('/check_email', methods=['POST', 'OPTIONS'])
def check_email():
    """Check if an email exists and get associated passwords"""
    if request.method == 'OPTIONS':
        return '', 200
    
    if not request.is_json:
        return jsonify({'exists': False, 'error': 'JSON required'}), 400
    
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    
    if not email or '@' not in email:
        return jsonify({'exists': False, 'error': 'Invalid email format'}), 400
    
    db = load_database()
    email_index = db.get('email_index', {})
    
    if email in email_index:
        passwords = email_index[email]
        return jsonify({
            'exists': True,
            'data': {
                'email': email,
                'passwords': passwords,
                'count': len(passwords)
            }
        })
    else:
        return jsonify({'exists': False, 'data': None})

@app.route('/check_username', methods=['POST', 'OPTIONS'])
def check_username():
    """Check if a username exists in the database"""
    if request.method == 'OPTIONS':
        return '', 200
    
    if not request.is_json:
        return jsonify({'exists': False, 'error': 'JSON required'}), 400
    
    data = request.get_json()
    username = data.get('username', '').strip().lower()
    
    if not username:
        return jsonify({'exists': False, 'error': 'Invalid username'}), 400
    
    db = load_database()
    username_index = db.get('username_index', {})
    
    if username in username_index:
        combos = username_index[username]
        return jsonify({
            'exists': True,
            'data': {
                'username': username,
                'count': len(combos),
                'first_seen': db.get('metadata', {}).get('date_added', 'Unknown')
            }
        })
    else:
        return jsonify({'exists': False, 'data': None})

@app.route('/stats', methods=['GET'])
def get_stats():
    """Get detailed database statistics"""
    db = load_database()
    
    combos = db.get('combos', [])
    total = len(combos)
    
    # Count unique domains in emails
    domains = defaultdict(int)
    for combo in combos:
        if ':' in combo:
            email_part = combo.split(':')[0]
            if '@' in email_part:
                domain = email_part.split('@')[1].lower()
                domains[domain] += 1
    
    top_domains = sorted(domains.items(), key=lambda x: x[1], reverse=True)[:10]
    
    return jsonify({
        'success': True,
        'total_combos': total,
        'total_hashes': len(db.get('hashes', [])),
        'unique_emails': len(db.get('email_index', {})),
        'unique_usernames': len(db.get('username_index', {})),
        'metadata': db.get('metadata', {}),
        'top_domains': top_domains
    })

@app.route('/clear', methods=['POST'])
def clear_database():
    """Clear the database"""
    secret = request.headers.get('X-Clear-Secret', '')
    if secret != 'clear_all_data_123':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    new_db = {
        "combos": [],
        "hashes": [],
        "email_index": {},
        "username_index": {},
        "metadata": {
            "total_lines": 0,
            "latest_added": 0,
            "date_added": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "added_by": "System (Cleared)"
        }
    }
    
    if save_database(new_db):
        return jsonify({'success': True, 'message': 'Database cleared successfully'})
    else:
        return jsonify({'success': False, 'error': 'Failed to clear database'}), 500

@app.route('/search', methods=['POST', 'OPTIONS'])
def search_database():
    """Search database by keyword"""
    if request.method == 'OPTIONS':
        return '', 200
    
    if not request.is_json:
        return jsonify({'success': False, 'error': 'JSON required'}), 400
    
    data = request.get_json()
    query = data.get('query', '').strip().lower()
    limit = min(data.get('limit', 50), 200)
    
    if not query:
        return jsonify({'success': False, 'error': 'No query provided'}), 400
    
    db = load_database()
    combos = db.get('combos', [])
    
    results = []
    for combo in combos:
        if query in combo.lower():
            results.append(combo)
            if len(results) >= limit:
                break
    
    return jsonify({
        'success': True,
        'query': query,
        'count': len(results),
        'results': results
    })

@app.route('/export', methods=['GET'])
def export_database():
    """Export database as JSON or text"""
    format_type = request.args.get('format', 'json')
    limit = int(request.args.get('limit', 10000))
    
    db = load_database()
    combos = db.get('combos', [])[:limit]
    
    if format_type == 'txt':
        text_response = '\n'.join(combos)
        return text_response, 200, {'Content-Type': 'text/plain'}
    else:
        return jsonify({
            'success': True,
            'total': len(db.get('combos', [])),
            'returned': len(combos),
            'combos': combos,
            'metadata': db.get('metadata', {})
        })

@app.route('/rebuild_indexes', methods=['POST'])
def rebuild_indexes():
    """Rebuild email and username indexes"""
    secret = request.headers.get('X-Clear-Secret', '')
    if secret != 'clear_all_data_123':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    db = load_database()
    combos = db.get('combos', [])
    
    # Rebuild indexes
    email_index = {}
    username_index = {}
    
    for combo in combos:
        # Email index
        if ':' in combo:
            email_part = combo.split(':')[0]
            if '@' in email_part:
                email = email_part.lower()
                if email not in email_index:
                    email_index[email] = []
                password = combo.split(':', 1)[1]
                if password not in email_index[email]:
                    email_index[email].append(password)
            
            # Username index
            username_part = combo.split(':')[0]
            if '@' not in username_part:
                username = username_part.lower()
                if username not in username_index:
                    username_index[username] = []
                if combo not in username_index[username]:
                    username_index[username].append(combo)
    
    db['email_index'] = email_index
    db['username_index'] = username_index
    
    if save_database(db):
        return jsonify({
            'success': True,
            'unique_emails': len(email_index),
            'unique_usernames': len(username_index),
            'total_combos': len(combos)
        })
    else:
        return jsonify({'success': False, 'error': 'Failed to save database'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print("=" * 60)
    print("🚀 ULTIMATE COMBO DATABASE SERVER v2.0")
    print("=" * 60)
    print(f"✅ Server starting on port {port}")
    print(f"📁 Database file: {DB_FILE}")
    print("=" * 60)
    print("📊 ENDPOINTS:")
    print("   GET  /                           - Server info")
    print("   GET  /health                     - Health check")
    print("   GET  /stats                      - Database statistics")
    print("   GET  /?action=metadata           - Get metadata")
    print("   GET  /export?format=txt          - Export database")
    print("   POST /                           - Compare combos")
    print("   POST /add_bulk_public            - Add combos (public)")
    print("   POST /check_combo                - Check combo exists")
    print("   POST /check_email                - Check email & passwords")
    print("   POST /check_username             - Check username")
    print("   POST /search                     - Search database")
    print("   POST /clear                      - Clear database (admin)")
    print("   POST /rebuild_indexes            - Rebuild indexes (admin)")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)