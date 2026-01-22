from flask import Flask, request, jsonify
import json
import os
import datetime

app = Flask(__name__)
DB_FILE = 'licenses.json'

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"keys": {}, "global_payload": ""}

def save_db(data):
    # Ensure keys are in a sub-key if not already
    if "keys" not in data:
        data = {"keys": data, "global_payload": ""}
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# 初期DB作成
if not os.path.exists(DB_FILE):
    save_db({"keys": {}, "global_payload": ""})

@app.route('/verify', methods=['POST'])
def verify_key():
    data = request.json
    key = data.get('key')
    hwid = data.get('hwid')
    
    db = load_db()
    
    if key not in db:
        return jsonify({"valid": False, "message": "Invalid Key"}), 404
        
    key_data = db[key]
    
    # 期限チェック
    if key_data['expiry'] != 'lifetime':
        try:
            exp_date = datetime.datetime.fromisoformat(key_data['expiry'])
            if datetime.datetime.now() > exp_date:
                return jsonify({"valid": False, "message": "Expired"}), 403
        except:
            pass # 日付形式エラーなどは一旦無視
            
    # HWIDチェック (初回は登録、または無制限の場合はチェックしない)
    hwid_limit = key_data.get('hwid_limit', 1)  # デフォルトは1台まで
    
    if hwid_limit == 'unlimited':
        # 無制限の場合はHWIDチェックをスキップ
        pass
    elif key_data['hwid'] is None:
        # 初回登録
        key_data['hwid'] = hwid
        save_db(db)
    elif key_data['hwid'] != hwid:
        return jsonify({"valid": False, "message": "HWID Mismatch"}), 403
        
    return jsonify({
        "valid": True, 
        "expiry": key_data['expiry'],
        "hwid": key_data.get('hwid', 'unlimited')
    })

@app.route('/admin/add_key', methods=['POST'])
def add_key():
    # 本来は管理者認証が必要ですが、簡易版のため省略
    data = request.json
    key = data.get('key')
    expiry = data.get('expiry', 'lifetime')
    
    db = load_db()
    if key in db:
        return jsonify({"success": False, "message": "Key exists"}), 400
    
    hwid_limit = data.get('hwid_limit', 1)  # デフォルトは1台まで
    
    db[key] = {
        "expiry": expiry,
        "hwid": None,
        "hwid_limit": hwid_limit
    }
    save_db(db)
    return jsonify({"success": True, "message": "Key added"})

@app.route('/admin/delete_key', methods=['POST'])
def delete_key():
    data = request.json
    key = data.get('key')
    
    db = load_db()
    if key in db:
        del db[key]
        save_db(db)
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Key not found"}), 404

@app.route('/admin/reset_hwid', methods=['POST'])
def reset_hwid():
    data = request.json
    key = data.get('key')
    
    db = load_db()
    if key in db:
        db[key]['hwid'] = None
        save_db(db)
        return jsonify({"success": True})
    return jsonify({"success": False}), 404

@app.route('/admin/list_keys', methods=['GET'])
def list_keys():
    db = load_db()
    return jsonify(db)

if __name__ == '__main__':
    # 外部公開する場合は host='0.0.0.0' にする
    app.run(host='0.0.0.0', port=5000)
