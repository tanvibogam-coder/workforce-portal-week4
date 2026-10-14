"""Enterprise Employee Performance & Workforce Operations Management Portal - Flask entry point."""
import os, logging
from pathlib import Path
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
import mysql.connector
import db
from auth import bp as auth_bp
from routes.employees import bp as emp_bp
from routes.time_off import bp as time_bp
from routes.work import bp as work_bp
from routes.insights import bp as insights_bp

FRONTEND = Path(__file__).resolve().parent.parent / 'frontend'


def create_app():
    app = Flask(__name__); CORS(app); app.config['MAX_CONTENT_LENGTH'] = 6 * 1024 * 1024
    for bp in (auth_bp, emp_bp, time_bp, work_bp, insights_bp): app.register_blueprint(bp, url_prefix='/api')

    @app.get('/api/health')
    def health():
        try: db.one('SELECT 1 AS ok'); return jsonify(status='ok', database='connected')
        except mysql.connector.Error: return jsonify(status='error', database='disconnected'), 500

    @app.errorhandler(Exception)
    def handle(e):  # centralised error handling: consistent {"error": "..."} shape, no internals leaked
        if isinstance(e, HTTPException): return jsonify(error=e.description), e.code
        if isinstance(e, ValueError): return jsonify(error='Invalid input value.'), 400
        logging.exception(e)
        return jsonify(error='Database error.' if isinstance(e, mysql.connector.Error) else 'Internal server error.'), 500

    @app.route('/', defaults={'path': 'index.html'})
    @app.route('/<path:path>')
    def frontend(path):
        if path.startswith('api/'): return jsonify(error='Not found.'), 404
        return send_from_directory(FRONTEND, path if (FRONTEND / path).is_file() else 'index.html')
    return app


app = create_app()
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.getenv('PORT', '5000')), debug=True)
