from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from datetime import datetime
import hashlib

app = Flask(__name__)
CORS(app)

# Database file path
DB_FILE = 'database.json'
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'YOUR_SECRET_ADMIN_KEY_HERE')

def load_database():
    """Load database from file"""
    if not os.path.exists(DB_FILE):
        return {
            "combos": [],
            "hashes": [],
            "metadata": {
                "total_lines": 0,
                "latest_added": 0,
                "date_added": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "added_by": "System"
            }
        }
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading database: {e}")
        return {
            "combos": [],
            "hashes": [],
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
                'metadata': db.get('metadata', {})
            })
        
        return jsonify({
            "status": "ok",
            "message": "Database server running",
            "endpoints": {
                "GET ?action=metadata": "Get database metadata",
                "GET ?action=stats": "Get detailed statistics",
                "POST with JSON": "Compare combos or add new combos"
            }
        })
    
    elif request.method == 'POST':
        # Handle JSON data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        
        # Compare combos with database
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
        
        # Add combos to database
        elif 'add_combos' in data:
            if data.get('admin_key') != ADMIN_KEY:
                return jsonify({
                    'success': False,
                    'error': 'Invalid admin key'
                }), 401
            
            new_combos_text = data['add_combos']
            new_combos = [c.strip() for c in new_combos_text.split('\n') if c.strip() and ':' in c]
            
            if not new_combos:
                return jsonify({
                    'success': False,
                    'error': 'No valid combos to add'
                }), 400
            
            db = load_database()
            existing_hashes = set(db.get('hashes', []))
            
            added_combos = []
            added_hashes = []
            
            for combo in new_combos:
                combo_hash = hash_combo(combo)
                if combo_hash not in existing_hashes:
                    existing_hashes.add(combo_hash)
                    added_combos.append(combo)
                    added_hashes.append(combo_hash)
            
            if 'combos' not in db:
                db['combos'] = []
            if 'hashes' not in db:
                db['hashes'] = []
            
            db['combos'].extend(added_combos)
            db['hashes'].extend(added_hashes)
            
            db['metadata'] = {
                'total_lines': len(db['combos']),
                'latest_added': len(added_combos),
                'date_added': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'added_by': data.get('added_by', 'Admin')
            }
            
            if save_database(db):
                return jsonify({
                    'success': True,
                    'added': len(added_combos),
                    'total': len(db['combos']),
                    'message': f"Added {len(added_combos)} new combos"
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to save database'
                }), 500
        
        return jsonify({
            'success': False,
            'error': 'Invalid request. Use "combos" or "add_combos" parameter'
        }), 400

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "database_exists": os.path.exists(DB_FILE)
    })

@app.route('/add_bulk', methods=['POST'])
def add_bulk():
    """Bulk add combos from file content"""
    if not request.is_json:
        return jsonify({'success': False, 'error': 'JSON required'}), 400
    
    data = request.get_json()
    
    if data.get('admin_key') != ADMIN_KEY:
        return jsonify({'success': False, 'error': 'Invalid admin key'}), 401
    
    combos_text = data.get('combos', '')
    added_by = data.get('added_by', 'Bulk Upload')
    
    combos = [c.strip() for c in combos_text.split('\n') if c.strip() and ':' in c]
    
    if not combos:
        return jsonify({'success': False, 'error': 'No valid combos found'}), 400
    
    db = load_database()
    existing_hashes = set(db.get('hashes', []))
    
    added_combos = []
    added = 0
    
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
            added_combos.append(combo)
            added += 1
    
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
            'total': len(db['combos']),
            'skipped': len(combos) - added,
            'sample_added': added_combos[:5]  # Show first 5 added as sample
        })
    else:
        return jsonify({'success': False, 'error': 'Failed to save'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"🚀 Starting database server on port {port}")
    print(f"🔑 Admin key set: {'✅ Yes' if ADMIN_KEY != 'YOUR_SECRET_ADMIN_KEY_HERE' else '⚠️ Using default'}")
    print(f"📁 Database file: {DB_FILE}")
    app.run(host='0.0.0.0', port=port, debug=False)