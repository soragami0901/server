from flask import Flask, request, jsonify
import json
import os
import datetime
from pymongo import MongoClient

app = Flask(__name__)

# MongoDB Connection
MONGO_URI = os.environ.get('MONGO_URI')

# Global client - Don't call server_info() at top level because it blocks Gunicorn boot
if MONGO_URI:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    print("MongoDB Client initialized (MONGO_URI found)")
else:
    # Local fallback or Dummy client to prevent NameError
    client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=2000)
    print("WARNING: MONGO_URI not found. Running with local fallback.")

db = client['lag_switch_pro']
keys_coll = db['keys']
settings_coll = db['settings']

def check_db_connection():
    """DB接続を確認（API呼び出し時に随時使用）"""
    try:
        client.admin.command('ping')
        return True
    except Exception as e:
        print(f"Database connection check FAILED: {e}")
        return False

def get_settings():
    """設定情報を取得（なければデフォルトを返す）"""
    try:
        settings = settings_coll.find_one({"type": "version"})
        if not settings:
            default_settings = {
                "type": "version",
                "number": "9.0",
                "download_url": "",
                "release_notes": "Database Migrated",
                "force_update": False,
                "released_at": datetime.datetime.now().isoformat()
            }
            settings_coll.insert_one(default_settings)
            return default_settings
        return settings
    except Exception as e:
        print(f"Database error in get_settings: {e}")
        return {}

@app.route('/verify', methods=['POST'])
def verify_key():
    try:
        data = request.json
        key = data.get('key')
        hwid = data.get('hwid')
        
        if not key:
            return jsonify({"valid": False, "message": "Key missing"}), 400

        key_data = keys_coll.find_one({"key": key})
        
        if not key_data:
            return jsonify({"valid": False, "message": "Invalid Key"}), 404
            
        # 期限チェック
        if key_data.get('expiry') != 'lifetime':
            try:
                exp_date = datetime.datetime.fromisoformat(key_data['expiry'])
                if datetime.datetime.now() > exp_date:
                    return jsonify({"valid": False, "message": "Expired"}), 403
            except:
                pass
                
        # HWIDチェック
        hwid_limit = key_data.get('hwid_limit', 1)
        
        if hwid_limit == 'unlimited':
            pass
        elif key_data.get('hwid') is None or key_data.get('hwid') == "":
            # 初回登録
            keys_coll.update_one({"key": key}, {"$set": {"hwid": hwid}})
        elif key_data['hwid'] != hwid:
            return jsonify({"valid": False, "message": "HWID Mismatch"}), 403
            
        return jsonify({
            "valid": True, 
            "expiry": key_data['expiry'],
            "hwid": key_data.get('hwid', 'unlimited')
        })
    except Exception as e:
        print(f"Error in verify_key: {e}")
        return jsonify({"valid": False, "message": f"Server DB Error: {str(e)}"}), 500

@app.route('/admin/add_key', methods=['POST'])
def add_key():
    try:
        data = request.json
        key = data.get('key')
        expiry = data.get('expiry', 'lifetime')
        hwid_limit = data.get('hwid_limit', 1)
        
        if not key:
            return jsonify({"success": False, "message": "Key name required"}), 400

        if keys_coll.find_one({"key": key}):
            return jsonify({"success": False, "message": "Key exists"}), 400
        
        keys_coll.insert_one({
            "key": key,
            "expiry": expiry,
            "hwid": None,
            "hwid_limit": hwid_limit,
            "created_at": datetime.datetime.now().isoformat()
        })
        return jsonify({"success": True, "message": "Key added"})
    except Exception as e:
        print(f"Error in add_key: {e}")
        return jsonify({"success": False, "message": f"Database Error: {str(e)}"}), 500

@app.route('/admin/delete_key', methods=['POST'])
def delete_key():
    try:
        data = request.json
        key = data.get('key')
        
        result = keys_coll.delete_one({"key": key})
        if result.deleted_count > 0:
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "Key not found"}), 404
    except Exception as e:
        print(f"Error in delete_key: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/admin/reset_hwid', methods=['POST'])
def reset_hwid():
    try:
        data = request.json
        key = data.get('key')
        
        result = keys_coll.update_one({"key": key}, {"$set": {"hwid": None}})
        if result.matched_count > 0:
            return jsonify({"success": True})
        return jsonify({"success": False}), 404
    except Exception as e:
        print(f"Error in reset_hwid: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/admin/list_keys', methods=['GET'])
def list_keys():
    try:
        # 全キーを辞書形式で返す（既存のクライアントとの互換性のため）
        keys = {}
        for k in keys_coll.find():
            keys[k['key']] = {
                "expiry": k['expiry'],
                "hwid": k.get('hwid'),
                "hwid_limit": k.get('hwid_limit', 1)
            }
        return jsonify(keys)
    except Exception as e:
        print(f"Error in list_keys: {e}")
        return jsonify({}), 500

@app.route('/version', methods=['GET'])
def get_version():
    settings = get_settings()
    return jsonify({
        "number": settings.get('number', '9.0'),
        "download_url": settings.get('download_url', ''),
        "release_notes": settings.get('release_notes', ''),
        "force_update": settings.get('force_update', False)
    })

@app.route('/admin/set_version', methods=['POST'])
    data = request.json
    version_number = data.get('version_number')
    download_url = data.get('download_url')
    release_notes = data.get('release_notes', '')
    force_update = data.get('force_update', False)
    code_content = data.get('code_content')

    if not version_number:
        return jsonify({"success": False, "message": "Version number required"}), 400
    
    update_data = {
        "number": version_number,
        "download_url": download_url,
        "release_notes": release_notes,
        "force_update": force_update,
        "released_at": datetime.datetime.now().isoformat()
    }
    
    if code_content:
        update_data['code_content'] = code_content
        # Auto-set download URL to this server
        update_data['download_url'] = f"{request.url_root.rstrip('/')}/update/script"

    settings_coll.update_one(
        {"type": "version"},
        {"$set": update_data},
        upsert=True
    )
    return jsonify({"success": True, "message": "Version updated"})

@app.route('/update/script', methods=['GET'])
def get_update_script():
    try:
        settings = settings_coll.find_one({"type": "version"})
        if not settings or 'code_content' not in settings:
            return "No update script found", 404
        
        # Return as downloadable file
        from flask import Response
        return Response(
            settings['code_content'],
            mimetype="text/x-python",
            headers={"Content-disposition": "attachment; filename=lag_switch.py"}
        )
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
