"""通用工具：统一响应体、业务异常、JSON 归一化、分页、单据编号、操作日志、站内消息。

响应体契约（PRD 6.1/6.3）：
  成功  {"code": 0, "message": "success", "data": {...}}
  失败  {"code": 40001..., "message": "...", "data": null}
  业务失败 HTTP 200；鉴权失败 HTTP 401 (code 40101)。
"""
import re
import uuid
from datetime import date, datetime
from decimal import Decimal

from flask import jsonify, request

from .db import q1

DT_FMT = '%Y-%m-%d %H:%M:%S'
DATE_FMT = '%Y-%m-%d'


class ApiError(Exception):
    """业务异常：code 为业务错误码，http 仅 401（鉴权失败）时非 200。"""

    def __init__(self, code, message, http=200):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http = http


def ok(data=None):
    return jsonify({'code': 0, 'message': 'success', 'data': data})


def _normalize(v):
    if isinstance(v, Decimal):
        s = format(v, 'f')
        return s
    if isinstance(v, datetime):
        return v.strftime(DT_FMT)
    if isinstance(v, date):
        return v.strftime(DATE_FMT)
    if isinstance(v, dict):
        return {k: _normalize(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_normalize(x) for x in v]
    return v


def json_payload(row):
    """把数据库行转成 JSON 安全结构（Decimal→str，datetime→字符串）。"""
    if row is None:
        return None
    return _normalize(row)


def get_params():
    """查询参数（GET）或 JSON 体（POST/PUT）统一读取。"""
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        body = request.get_json(silent=True)
        if isinstance(body, dict):
            return body
        return {}
    return request.args.to_dict()


def page_args(params):
    try:
        page = max(1, int(params.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        size = int(params.get('size', 10))
    except (TypeError, ValueError):
        size = 10
    size = min(max(size, 1), 100)  # 上限 100（PRD 6.1）
    return page, size


def page_data(rows, total, page, size):
    return {'list': json_payload(rows), 'total': total, 'page': page, 'size': size}


def client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr or '') or ''


def doc_no(conn, prefix):
    """单据编号：前缀-YYYYMMDD-4位流水（按日重置；作废不复用——序列只增不减）。"""
    today = datetime.now().strftime('%Y%m%d')
    row = q1(
        conn,
        """
        INSERT INTO sys_seq (biz_date, prefix, cur) VALUES (current_date, %s, 1)
        ON CONFLICT (biz_date, prefix) DO UPDATE SET cur = sys_seq.cur + 1
        RETURNING cur
        """,
        (prefix,),
    )
    return '%s-%s-%04d' % (prefix, today, row['cur'])


def op_log(conn, ctx, biz_type, biz_id, action, before=None, after=None):
    """所有写操作强制留痕（PRD 7 可审计性）。"""
    from .db import execute
    execute(
        conn,
        """
        INSERT INTO sys_operation_log (user_id, company_id, biz_type, biz_id, action,
                                       before_value, after_value, ip)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            ctx.user['id'] if ctx and ctx.user else None,
            ctx.company['id'] if ctx and ctx.company else None,
            biz_type, biz_id, action,
            _dump(before), _dump(after), client_ip(),
        ),
    )


def _dump(v):
    import json
    if v is None:
        return None
    return json.dumps(json_payload(v), ensure_ascii=False)


def send_msg(conn, receiver_company_id, title, content, biz_type=None, biz_id=None):
    """站内消息（一期简化项：只写消息表 + 页面提示）。"""
    from .db import execute
    execute(
        conn,
        """
        INSERT INTO sys_message (receiver_company_id, title, content, biz_type, biz_id)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (receiver_company_id, title, content, biz_type, biz_id),
    )


CREDIT_CODE_RE = re.compile(r'^[0-9A-HJ-NPQRTUWXY]{18}$')
PHONE_RE = re.compile(r'^1\d{10}$')


def validate_credit_code(code):
    if not code or not CREDIT_CODE_RE.match(code):
        raise ApiError(40001, '统一社会信用代码格式不正确')


def validate_phone(phone):
    if not phone or not PHONE_RE.match(str(phone)):
        raise ApiError(40001, '手机号格式不正确')


def validate_password(pwd):
    """密码长度≥8位，须同时包含字母和数字（PRD 4.1）。"""
    if not pwd or len(pwd) < 8 or not re.search(r'[A-Za-z]', pwd) or not re.search(r'\d', pwd):
        raise ApiError(40001, '密码长度至少8位，且须同时包含字母和数字')


def require_fields(params, *names):
    for n in names:
        v = params.get(n)
        if v is None or (isinstance(v, str) and v.strip() == ''):
            raise ApiError(40001, '参数缺失：%s' % n)


def decimal_field(params, name, positive=True, required=True):
    v = params.get(name)
    if v is None or v == '':
        if required:
            raise ApiError(40001, '参数缺失：%s' % name)
        return None
    try:
        d = Decimal(str(v))
    except Exception:
        raise ApiError(40001, '参数格式错误：%s' % name)
    if required and positive and d <= 0:
        raise ApiError(40001, '%s 必须大于0' % name)
    return d


def parse_date(params, name, required=True):
    v = params.get(name)
    if v is None or v == '':
        if required:
            raise ApiError(40001, '参数缺失：%s' % name)
        return None
    try:
        return datetime.strptime(str(v)[:10], DATE_FMT).date()
    except ValueError:
        raise ApiError(40001, '日期格式错误：%s（应为 yyyy-MM-dd）' % name)


def parse_datetime(params, name, required=True):
    v = params.get(name)
    if v is None or v == '':
        if required:
            raise ApiError(40001, '参数缺失：%s' % name)
        return None
    s = str(v)
    for f in (DT_FMT, '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(s[:19], f)
        except ValueError:
            continue
    raise ApiError(40001, '时间格式错误：%s（应为 yyyy-MM-dd HH:mm:ss）' % name)
