-- BUG-06 一次性数据迁移：历史时间戳 UTC → Asia/Shanghai（+8 小时）
--
-- 根因：PostgreSQL 容器默认时区为 Etc/UTC，所有由数据库 now() 生成的时间戳
--       （created_at/updated_at 及各类动作时间）为 UTC 墙钟时间，比业务
--       时间（用户按本地 Asia/Shanghai 语义输入的 deadline 等）慢 8 小时。
-- 代码修复：backend/db.py / backend/__init__.py 已将会话时区固定为
--       Asia/Shanghai（环境变量 MINE_PG_TZ 可覆盖），docker-compose.yml 已
--       补充 TZ/PGTZ。本脚本仅迁移"修复部署前"已产生的历史数据。
--
-- 迁移范围（仅数据库 now() 生成的列）：
--   1. 全部表的 created_at / updated_at（DEFAULT now() 或 SQL now() 写入）
--   2. 动作时间列中由 SQL now() 生成的：sent_at / handled_at /
--      supplier_confirm_at / buyer_confirm_at / buyer_sign_at / supplier_sign_at
--   3. biz_track_node.occur_time 中 source='SYSTEM' 的行（COALESCE(occur, now())）
--
-- 明确不迁移（非数据库生成，本就是本地时间语义）：
--   biz_inquiry.deadline / biz_order.confirm_deadline（业务时间字段）；
--   biz_waybill.actual_depart_at / actual_arrive_at（Python datetime.now() 或用户手填）；
--   biz_track_node.occur_time 中手工节点（source<>'SYSTEM'）。
--
-- 执行顺序：在部署含会话时区修复的新版后端之前执行（保证库内全部
-- now() 时间戳均为 UTC 语义）；执行后新写入即时为北京时间。

BEGIN;

-- 1) 全部表 created_at / updated_at
UPDATE base_price         SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';
UPDATE base_variety       SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';
UPDATE biz_alert          SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';
UPDATE biz_bargain        SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';
UPDATE biz_contract       SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';
UPDATE biz_demand         SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';
UPDATE biz_demand_item    SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';
UPDATE biz_forecast_quote SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';
UPDATE biz_inquiry        SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';
UPDATE biz_inquiry_invite SET created_at=created_at+interval '8 hours';
UPDATE biz_logistics_plan SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';
UPDATE biz_order          SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';
UPDATE biz_payment        SET created_at=created_at+interval '8 hours';
UPDATE biz_quality_check  SET created_at=created_at+interval '8 hours';
UPDATE biz_quote          SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';
UPDATE biz_settlement     SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';
UPDATE biz_track_node     SET created_at=created_at+interval '8 hours';
UPDATE biz_waybill        SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';
UPDATE ent_company        SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';
UPDATE ent_qualification  SET created_at=created_at+interval '8 hours';
UPDATE sys_file           SET created_at=created_at+interval '8 hours';
UPDATE sys_message        SET created_at=created_at+interval '8 hours';
UPDATE sys_operation_log  SET created_at=created_at+interval '8 hours';
UPDATE sys_user           SET created_at=created_at+interval '8 hours', updated_at=updated_at+interval '8 hours';

-- 2) SQL now() 生成的动作时间列（空值跳过）
UPDATE biz_inquiry    SET sent_at=sent_at+interval '8 hours'             WHERE sent_at IS NOT NULL;
UPDATE biz_alert      SET handled_at=handled_at+interval '8 hours'       WHERE handled_at IS NOT NULL;
UPDATE biz_settlement SET supplier_confirm_at=supplier_confirm_at+interval '8 hours' WHERE supplier_confirm_at IS NOT NULL;
UPDATE biz_settlement SET buyer_confirm_at=buyer_confirm_at+interval '8 hours'       WHERE buyer_confirm_at IS NOT NULL;
UPDATE biz_contract   SET buyer_sign_at=buyer_sign_at+interval '8 hours'             WHERE buyer_sign_at IS NOT NULL;
UPDATE biz_contract   SET supplier_sign_at=supplier_sign_at+interval '8 hours'       WHERE supplier_sign_at IS NOT NULL;

-- 3) 系统履约节点（手工节点与 Python 本地时间写入的不迁移）
UPDATE biz_track_node SET occur_time=occur_time+interval '8 hours' WHERE source='SYSTEM';

COMMIT;
