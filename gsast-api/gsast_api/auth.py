from functools import wraps
from hmac import compare_digest

from flask import request, jsonify, g


def requires_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'API-SECRET-KEY' not in request.headers or not compare_digest(
            request.headers['API-SECRET-KEY'], g.API_SECRET_KEY
        ):
            return jsonify({'error': 'Invalid API-SECRET-KEY'}), 403
        return f(*args, **kwargs)

    return decorated_function
