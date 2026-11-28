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

from flask import has_request_context, jsonify, request

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
    """查询参数（GET）或 JSON 体（POST/PUT）统一读取。DELETE 无 JSON 体时回退读取查询参数。"""
    if request.method in ('POST', 'PUT', 'PATCH'):
        body = request.get_json(silent=True)
        if isinstance(body, dict):
            return body
        return {}
    # DELETE 常以查询参数携带字段（如删除理由 ?reason=xxx），无体时回退 args
    body = request.get_json(silent=True)
    if isinstance(body, dict):
        args = request.args.to_dict()
        args.update(body)
        return args
    return request.args.to_dict()


def page_args(params):
    try:
        page = max(1, int(params.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    # P3-2：页码上限 10000，防恶意深分页引发全量扫描（size 上限 100，PRD 6.1）
    page = min(page, 10000)
    try:
        size = int(params.get('size', 10))
    except (TypeError, ValueError):
        size = 10
    size = min(max(size, 1), 100)  # 上限 100（PRD 6.1）
    return page, size


def page_data(rows, total, page, size):
    return {'list': json_payload(rows), 'total': total, 'page': page, 'size': size}


def client_ip():
    """客户端 IP（审计留痕用）。

    P0-0 修复：无请求上下文（后台线程/定时任务经 op_log 调用）时返回 'SYSTEM'。
    原实现对 flask.request 裸访问，jobs 线程一进 op_log 即抛 RuntimeError，
    导致"状态已变、审计缺失"的半提交被固化。
    P3-1 加固：X-Forwarded-For 取首个有效地址（多级代理逗号串不再整段入库）。
    注意该头可伪造，可信度取决于前置代理是否重写，仅作审计佐证。
    """
    if not has_request_context():
        return 'SYSTEM'
    xff = (request.headers.get('X-Forwarded-For') or '').strip()
    if xff:
        first = xff.split(',')[0].strip()[:64]
        if first and IP_TOKEN_RE.match(first):
            return first
    return request.remote_addr or ''


# X-Forwarded-For 首段合法性：IPv4/IPv6 常见字符（防脏数据原样入库）
IP_TOKEN_RE = re.compile(r'^[0-9A-Fa-f.:]+$')


def doc_no(conn, prefix):
    """单据编号：前缀-YYYYMMDD-4位流水（按日重置；作废不复用——序列只增不减）。

    P2-3 说明（性能热点）：计数行锁自 UPDATE 起持有至事务提交，所有写单据请求
    在该行串行。实测审计冒烟 QPS 283.9 / p95 139ms 尚未触及瓶颈；改为独立短事务
    发号需从连接池借第二个连接，池耗尽时有级联等待风险，维持现状并在此记录。
    业务量增长（>1000 单/日写入）时再评估块分配方案。
    """
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
    """审计 before/after 序列化。

    P3-4 加固：json_payload 之外的不可序列化结构（自定义对象/二进制等）此前会
    抛 TypeError 使整条审计失败（连带触发 P1-2 链）；现 default=str 兜底 +
    外层 try 保证审计留痕永不因序列化失败而中断。
    """
    import json
    if v is None:
        return None
    try:
        return json.dumps(json_payload(v), ensure_ascii=False, default=str)
    except Exception:
        try:
            return json.dumps({'_repr': repr(v)}, ensure_ascii=False)
        except Exception:
            return repr(v)


def send_msg(conn, receiver_company_id, title, content, biz_type=None, biz_id=None,
             msg_category='NOTICE', need_action=False):
    """站内消息（一期简化项：只写消息表 + 页面提示）。

    msg_category: NOTICE 通知 / WARN 预警 / ANNOUNCE 公告 / ACTIVITY 活动信息。
    need_action: True=需要接收端后续操作（消息提醒板块归类为「任务」）；False=纯通知（「消息」）。
    sender_company_id: 发布企业（自动取当前请求上下文的企业；空=运营端/平台发布）。
    """
    from .db import execute
    sender = None
    try:
        from flask import has_request_context, g
        if has_request_context():
            ctx = getattr(g, 'ctx', None)
            if ctx is not None and getattr(ctx, 'company', None):
                sender = ctx.company['id']
    except Exception:
        sender = None
    execute(
        conn,
        """
        INSERT INTO sys_message (receiver_company_id, title, content, biz_type, biz_id, msg_category,
                                 need_action, sender_company_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (receiver_company_id, title, content, biz_type, biz_id, msg_category,
         bool(need_action), sender),
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
    # P3-3：正数校验不再受 required 影响——可选数字字段一旦传值同样拒绝 0/负
    # （如 settlement.settleQty 选填传 0 绕过校验）；允许 0 的字段用 positive=False 显式声明
    if positive and d <= 0:
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
