"""API 蓝图聚合：/api/v1 前缀，各业务模块分包注册（PRD 8 工程约定）。"""
from flask import Blueprint

bp = Blueprint('api', __name__, url_prefix='/api/v1')

# 导入即注册路由（保持与 PRD 6.2 接口清单一致）
from . import auth      # noqa: E402,F401  登录注册
from . import company   # noqa: E402,F401  企业档案
from . import files     # noqa: E402,F401  附件
from . import base      # noqa: E402,F401  品种与基准价
from . import admin     # noqa: E402,F401  运营后台
from . import demand    # noqa: E402,F401  需求申报
from . import forecast  # noqa: E402,F401  远期预报
from . import inquiry   # noqa: E402,F401  询价与报价
from . import bargain   # noqa: E402,F401  议价
from . import order     # noqa: E402,F401  订单与定标
from . import contract  # noqa: E402,F401  合同
from . import logistics  # noqa: E402,F401 物流方案与运单
from . import track     # noqa: E402,F401  履约时间轴
from . import alert     # noqa: E402,F401  预警
from . import settlement  # noqa: E402,F401 质检/结算/付款/归档
from . import message   # noqa: E402,F401  站内消息
