--
-- PostgreSQL database dump
--

\restrict tK7pRfonraDYDMGz4UD34fMVbVxrxTJVh90XmthIud5sBWvFwb7uSrbiy8z4eAe

-- Dumped from database version 14.24 (Debian 14.24-1.pgdg13+2)
-- Dumped by pg_dump version 14.24 (Debian 14.24-1.pgdg13+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: base_price; Type: TABLE DATA; Schema: public; Owner: postgres
--

INSERT INTO public.base_price VALUES (2, 7, '2026-11-08', 862.00, 'WET', '中华混一号港口现货基准（E2E）', NULL, '2026-11-07 17:32:24.452187', '2026-11-07 17:34:18.869128', 1, 1, 0);
INSERT INTO public.base_price VALUES (6, 6, '2026-11-08', 830.50, 'WET', 'E2E 当日更新', NULL, '2026-11-07 18:27:45.894652', '2026-11-07 18:27:45.939382', 1, 1, 0);


--
-- Data for Name: base_variety; Type: TABLE DATA; Schema: public; Owner: postgres
--

INSERT INTO public.base_variety VALUES (7, 'ZHHYH', '中华混一号', 62.00, '吨', 0, 'ENABLED', '2026-11-07 16:08:05.097191', '2026-11-07 16:08:05.097191', 1, 1, 0);
INSERT INTO public.base_variety VALUES (6, 'PB', 'PB粉', 61.50, '吨', 0, 'ENABLED', '2026-11-07 16:07:48.880683', '2026-11-07 18:25:34.629789', 1, 1, 0);


--
-- Data for Name: biz_alert; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: biz_bargain; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: biz_contract; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: biz_demand; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: biz_demand_item; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: biz_forecast_quote; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: biz_inquiry; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: biz_inquiry_invite; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: biz_logistics_plan; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: biz_order; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: biz_payment; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: biz_quality_check; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: biz_quote; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: biz_settlement; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: biz_track_node; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: biz_waybill; Type: TABLE DATA; Schema: public; Owner: postgres
--



--
-- Data for Name: ent_company; Type: TABLE DATA; Schema: public; Owner: postgres
--

INSERT INTO public.ent_company VALUES (27, '测试承运物流有限公司', '91130100MA0DCAWK8P', 'LOGISTICS', '河北省', '唐山市', '曹妃甸工业区', NULL, '张承运', '13900000003', NULL, NULL, NULL, NULL, 'APPROVED', 'E2E承运商准入', 'ENABLED', '2026-11-07 17:42:00.206573', '2026-11-07 17:42:02.334794', 28, 1, 0);
INSERT INTO public.ent_company VALUES (25, '中国矿产资源集团国际铁矿石贸易有限公司', '91110000MA0CABCD1X', 'SUPPLIER', '上海', '上海市', '上海市虹口区东大名路700号', '张矿', '王矿', '13811110001', 'ore@cmgroup-demo.cn', '铁矿石及其他矿产资源贸易、代理采购与分销', '中国工商银行上海分行', '10012345678901234567', 'APPROVED', 'E2E测试：资质齐全，同意准入', 'ENABLED', '2026-11-07 17:01:29.205031', '2026-11-07 17:07:48.130727', 26, 1, 0);
INSERT INTO public.ent_company VALUES (26, '河北普阳钢铁有限公司', '91130400MA0DEFGH2K', 'STEEL', '河北', '邯郸市', '河北省邯郸市武安市阳邑镇', '郭普', '李钢', '13822220002', 'contact@puyang-demo.cn', '钢铁冶炼、钢材加工与铁矿石采购', '中国建设银行邯郸分行', '13012345678901234567', 'APPROVED', 'E2E测试：资质齐全，同意准入', 'ENABLED', '2026-11-07 17:03:27.780379', '2026-11-07 17:07:29.943761', 27, 1, 0);


--
-- Data for Name: ent_qualification; Type: TABLE DATA; Schema: public; Owner: postgres
--

INSERT INTO public.ent_qualification VALUES (20, 25, '9c0b5e0f6772452fbd46c02c0abd5a7c', 'license_cmgroup.png', 'BUSINESS_LICENSE', '2026-11-07 17:01:29.205031', 26, 0);
INSERT INTO public.ent_qualification VALUES (21, 26, '5366e250567b4f8c82cc24928abf9f83', 'license_puyang.png', 'BUSINESS_LICENSE', '2026-11-07 17:03:27.780379', 27, 0);
INSERT INTO public.ent_qualification VALUES (22, 27, '058b5d5b9db94638b893b6930d5c817a', 'carrier_license.png', 'BUSINESS_LICENSE', '2026-11-07 17:42:00.206573', 28, 0);


--
-- Data for Name: sys_file; Type: TABLE DATA; Schema: public; Owner: postgres
--

INSERT INTO public.sys_file VALUES (64, '058b5d5b9db94638b893b6930d5c817a', 'carrier_license.png', 'image/png', 70, 'E:\TRAE\mine_platform_demo\uploads\058b5d5b9db94638b893b6930d5c817a.png', NULL, '2026-11-07 17:41:58.141535', NULL, 0);
INSERT INTO public.sys_file VALUES (60, '9c0b5e0f6772452fbd46c02c0abd5a7c', 'license_cmgroup.png', 'image/png', 23206, 'E:\TRAE\mine_platform_demo\uploads\9c0b5e0f6772452fbd46c02c0abd5a7c.png', NULL, '2026-11-07 17:01:29.181956', NULL, 0);
INSERT INTO public.sys_file VALUES (61, '5366e250567b4f8c82cc24928abf9f83', 'license_puyang.png', 'image/png', 21684, 'E:\TRAE\mine_platform_demo\uploads\5366e250567b4f8c82cc24928abf9f83.png', NULL, '2026-11-07 17:03:27.757276', NULL, 0);


--
-- Data for Name: sys_message; Type: TABLE DATA; Schema: public; Owner: postgres
--

INSERT INTO public.sys_message VALUES (279, 27, '准入审核通过', 'E2E承运商准入', 'COMPANY', 27, 0, '2026-11-07 17:42:02.334794');
INSERT INTO public.sys_message VALUES (268, 26, '准入审核通过', 'E2E测试：资质齐全，同意准入', 'COMPANY', 26, 0, '2026-11-07 17:07:29.943761');
INSERT INTO public.sys_message VALUES (269, 25, '准入审核通过', 'E2E测试：资质齐全，同意准入', 'COMPANY', 25, 0, '2026-11-07 17:07:48.130727');


--
-- Data for Name: sys_operation_log; Type: TABLE DATA; Schema: public; Owner: postgres
--

INSERT INTO public.sys_operation_log VALUES (1085, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:32:15.986722');
INSERT INTO public.sys_operation_log VALUES (1130, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:37:58.508101');
INSERT INTO public.sys_operation_log VALUES (1159, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:41:51.528119');
INSERT INTO public.sys_operation_log VALUES (1183, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:43:40.790922');
INSERT INTO public.sys_operation_log VALUES (1205, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:13:56.193973');
INSERT INTO public.sys_operation_log VALUES (1226, 27, 26, 'biz_demand', 4, 'STATUS DRAFT->SUBMITTED', '{"status": "DRAFT", "version": 1}', '{"status": "SUBMITTED", "version": 1}', '127.0.0.1', '2026-11-07 18:17:02.548062');
INSERT INTO public.sys_operation_log VALUES (1259, 27, 26, 'biz_contract', 3, 'STATUS PENDING_GENERATE->PENDING_BUYER', '{"status": "PENDING_GENERATE"}', '{"status": "PENDING_BUYER"}', '127.0.0.1', '2026-11-07 18:17:04.344958');
INSERT INTO public.sys_operation_log VALUES (1260, 27, 26, 'biz_order', 2, 'STATUS PENDING_CONTRACT->PENDING_EFFECT', '{"status": "PENDING_CONTRACT"}', '{"status": "PENDING_EFFECT"}', '127.0.0.1', '2026-11-07 18:17:04.344958');
INSERT INTO public.sys_operation_log VALUES (1261, 27, 26, 'biz_contract', 3, 'GENERATE', NULL, '{"version": 2}', '127.0.0.1', '2026-11-07 18:17:04.344958');
INSERT INTO public.sys_operation_log VALUES (1292, 27, 26, 'biz_quality_check', 4, 'CREATE', NULL, '{"checkNo": "ZJ-20261108-0005", "arrivedQty": "20500", "conclusion": "ACCEPT"}', '127.0.0.1', '2026-11-07 18:17:05.671117');
INSERT INTO public.sys_operation_log VALUES (1314, NULL, NULL, 'sys_user', 31, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:20:35.421175');
INSERT INTO public.sys_operation_log VALUES (1342, 31, 30, 'biz_order', 3, 'STATUS PENDING_CONFIRM->PENDING_CONTRACT', '{"status": "PENDING_CONFIRM"}', '{"status": "PENDING_CONTRACT"}', '127.0.0.1', '2026-11-07 18:20:37.17368');
INSERT INTO public.sys_operation_log VALUES (1380, 27, 26, 'biz_quality_check', 5, 'CREATE', NULL, '{"checkNo": "ZJ-20261108-0006", "arrivedQty": "25000", "conclusion": "ACCEPT"}', '127.0.0.1', '2026-11-07 18:20:38.431539');
INSERT INTO public.sys_operation_log VALUES (1402, 1, NULL, 'base_price', 5, 'CREATE', NULL, '{"varietyId": 6, "priceDate": "2026-11-08", "price": 820.5, "priceBasis": "WET", "sourceDesc": "E2E 录入"}', '127.0.0.1', '2026-11-07 18:22:37.980374');
INSERT INTO public.sys_operation_log VALUES (1430, 27, 26, 'biz_contract', 6, 'STATUS PENDING_GENERATE->PENDING_BUYER', '{"status": "PENDING_GENERATE"}', '{"status": "PENDING_BUYER"}', '127.0.0.1', '2026-11-07 18:22:39.544216');
INSERT INTO public.sys_operation_log VALUES (1431, 27, 26, 'biz_order', 4, 'STATUS PENDING_CONTRACT->PENDING_EFFECT', '{"status": "PENDING_CONTRACT"}', '{"status": "PENDING_EFFECT"}', '127.0.0.1', '2026-11-07 18:22:39.544216');
INSERT INTO public.sys_operation_log VALUES (1432, 27, 26, 'biz_contract', 6, 'GENERATE', NULL, '{"version": 1}', '127.0.0.1', '2026-11-07 18:22:39.544216');
INSERT INTO public.sys_operation_log VALUES (1468, 27, 26, 'biz_alert', 6, 'STATUS PENDING->PROCESSING', '{"status": "PENDING"}', '{"status": "PROCESSING"}', '127.0.0.1', '2026-11-07 18:22:40.76955');
INSERT INTO public.sys_operation_log VALUES (1490, 1, NULL, 'ent_company', 35, 'STATUS PENDING->APPROVED', '{"status": "PENDING"}', '{"status": "APPROVED"}', '127.0.0.1', '2026-11-07 18:27:45.259953');
INSERT INTO public.sys_operation_log VALUES (1514, 37, 36, 'biz_bargain', 14, 'STATUS PENDING->ACCEPTED', '{"status": "PENDING"}', '{"status": "ACCEPTED"}', '127.0.0.1', '2026-11-07 18:27:47.227507');
INSERT INTO public.sys_operation_log VALUES (1553, 28, 27, 'biz_waybill', 9, 'STATUS PENDING_ACCEPT->PENDING_DEPART', '{"status": "PENDING_ACCEPT"}', '{"status": "PENDING_DEPART"}', '127.0.0.1', '2026-11-07 18:27:48.849015');
INSERT INTO public.sys_operation_log VALUES (1086, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:32:18.110891');
INSERT INTO public.sys_operation_log VALUES (1131, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:38:41.339718');
INSERT INTO public.sys_operation_log VALUES (1160, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:41:53.660977');
INSERT INTO public.sys_operation_log VALUES (1184, NULL, NULL, 'sys_user', 28, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:43:43.16639');
INSERT INTO public.sys_operation_log VALUES (1206, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:13:56.325046');
INSERT INTO public.sys_operation_log VALUES (1227, 27, 26, 'biz_demand', 4, 'STATUS SUBMITTED->WITHDRAWN', '{"status": "SUBMITTED"}', '{"status": "WITHDRAWN"}', '127.0.0.1', '2026-11-07 18:17:02.604709');
INSERT INTO public.sys_operation_log VALUES (1262, 27, 26, 'biz_contract', 3, 'STATUS PENDING_BUYER->PENDING_SUPPLIER', '{"status": "PENDING_BUYER"}', '{"status": "PENDING_SUPPLIER"}', '127.0.0.1', '2026-11-07 18:17:04.41353');
INSERT INTO public.sys_operation_log VALUES (1263, 27, 26, 'biz_contract', 3, 'SIGN(需方)', NULL, '{"signerName": "需方经办", "fileSha256": "4b8f3ce960bc6d4fda6aee1099f7d37530ae5a8e719e163c1f1ed1036e5f8a11"}', '127.0.0.1', '2026-11-07 18:17:04.41353');
INSERT INTO public.sys_operation_log VALUES (1293, 27, 26, 'biz_settlement', 2, 'CREATE', NULL, '{"settleNo": "JS-20261108-0002", "totalAmount": "16523000.00"}', '127.0.0.1', '2026-11-07 18:17:05.738559');
INSERT INTO public.sys_operation_log VALUES (1315, 1, NULL, 'base_price', 4, 'CREATE', NULL, '{"varietyId": 6, "priceDate": "2026-11-08", "price": 820.5, "priceBasis": "WET", "sourceDesc": "E2E 录入"}', '127.0.0.1', '2026-11-07 18:20:35.580034');
INSERT INTO public.sys_operation_log VALUES (1080, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:25:39.469667');
INSERT INTO public.sys_operation_log VALUES (1343, 27, 26, 'biz_contract', 4, 'STATUS PENDING_GENERATE->PENDING_BUYER', '{"status": "PENDING_GENERATE"}', '{"status": "PENDING_BUYER"}', '127.0.0.1', '2026-11-07 18:20:37.230517');
INSERT INTO public.sys_operation_log VALUES (1344, 27, 26, 'biz_order', 3, 'STATUS PENDING_CONTRACT->PENDING_EFFECT', '{"status": "PENDING_CONTRACT"}', '{"status": "PENDING_EFFECT"}', '127.0.0.1', '2026-11-07 18:20:37.230517');
INSERT INTO public.sys_operation_log VALUES (1345, 27, 26, 'biz_contract', 4, 'GENERATE', NULL, '{"version": 1}', '127.0.0.1', '2026-11-07 18:20:37.230517');
INSERT INTO public.sys_operation_log VALUES (1381, 27, 26, 'biz_alert', 4, 'STATUS PENDING->PROCESSING', '{"status": "PENDING"}', '{"status": "PROCESSING"}', '127.0.0.1', '2026-11-07 18:20:38.492277');
INSERT INTO public.sys_operation_log VALUES (1403, 1, NULL, 'base_price', 5, 'UPDATE', '{"id": 5, "variety_id": 6, "price_date": "2026-11-08", "price": "820.50", "price_basis": "WET", "source_desc": "E2E 录入", "remark": null, "created_at": "2026-11-07 18:22:37", "updated_at": "2026-11-07 18:22:37", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"price": 830.5, "priceBasis": "WET"}', '127.0.0.1', '2026-11-07 18:22:38.029009');
INSERT INTO public.sys_operation_log VALUES (1433, 27, 26, 'sys_file', 79, 'UPLOAD', NULL, '{"fileName": "stamp-buyer-1108022236.pdf", "size": 28}', '127.0.0.1', '2026-11-07 18:22:39.669522');
INSERT INTO public.sys_operation_log VALUES (1469, 27, 26, 'biz_alert', 6, 'STATUS PROCESSING->CLOSED', '{"status": "PROCESSING"}', '{"status": "CLOSED"}', '127.0.0.1', '2026-11-07 18:22:40.820778');
INSERT INTO public.sys_operation_log VALUES (1491, 1, NULL, 'ent_company', 36, 'STATUS PENDING->APPROVED', '{"status": "PENDING"}', '{"status": "APPROVED"}', '127.0.0.1', '2026-11-07 18:27:45.290356');
INSERT INTO public.sys_operation_log VALUES (1515, 27, 26, 'biz_bargain', 15, 'CREATE', NULL, '{"quoteId": 13, "roundNo": 3, "initiator": "BUYER"}', '127.0.0.1', '2026-11-07 18:27:47.258797');
INSERT INTO public.sys_operation_log VALUES (1554, 28, 27, 'biz_waybill', 9, 'STATUS PENDING_DEPART->IN_TRANSIT', '{"status": "PENDING_DEPART"}', '{"status": "IN_TRANSIT"}', '127.0.0.1', '2026-11-07 18:27:48.878233');
INSERT INTO public.sys_operation_log VALUES (1555, 28, 27, 'biz_waybill', 9, 'NODE DEPART', NULL, '{"node": "DEPART"}', '127.0.0.1', '2026-11-07 18:27:48.878233');
INSERT INTO public.sys_operation_log VALUES (1081, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:25:39.625159');
INSERT INTO public.sys_operation_log VALUES (1087, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:32:20.244246');
INSERT INTO public.sys_operation_log VALUES (1109, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:34:10.412955');
INSERT INTO public.sys_operation_log VALUES (1132, 26, 25, 'biz_inquiry', 2, 'STATUS CLOSED->BARGAINING', '{"status": "CLOSED"}', '{"status": "BARGAINING"}', '127.0.0.1', '2026-11-07 17:38:41.491558');
INSERT INTO public.sys_operation_log VALUES (1133, 26, 25, 'biz_bargain', 1, 'CREATE', NULL, '{"quoteId": 1, "roundNo": 1, "initiator": "SUPPLIER"}', '127.0.0.1', '2026-11-07 17:38:41.491558');
INSERT INTO public.sys_operation_log VALUES (1161, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:41:55.791527');
INSERT INTO public.sys_operation_log VALUES (1185, 27, 26, 'biz_alert', 1, 'STATUS PENDING->PROCESSING', '{"status": "PENDING"}', '{"status": "PROCESSING"}', '127.0.0.1', '2026-11-07 17:44:01.083574');
INSERT INTO public.sys_operation_log VALUES (1207, NULL, NULL, 'sys_user', 28, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:13:56.40719');
INSERT INTO public.sys_operation_log VALUES (1228, 27, 26, 'biz_demand', 4, 'STATUS WITHDRAWN->SUBMITTED', '{"status": "WITHDRAWN", "version": 1}', '{"status": "SUBMITTED", "version": 2}', '127.0.0.1', '2026-11-07 18:17:02.656491');
INSERT INTO public.sys_operation_log VALUES (1264, 31, 30, 'sys_file', 70, 'UPLOAD', NULL, '{"fileName": "stamp-supplier-1108021659.png", "size": 28}', '127.0.0.1', '2026-11-07 18:17:04.470234');
INSERT INTO public.sys_operation_log VALUES (1294, 31, 30, 'biz_settlement', 2, 'STATUS PENDING_CONFIRM_SUPPLIER->PENDING_CONFIRM_BUYER', '{"status": "PENDING_CONFIRM_SUPPLIER"}', '{"status": "PENDING_CONFIRM_BUYER"}', '127.0.0.1', '2026-11-07 18:17:05.823414');
INSERT INTO public.sys_operation_log VALUES (1316, 1, NULL, 'base_price', 4, 'UPDATE', '{"id": 4, "variety_id": 6, "price_date": "2026-11-08", "price": "820.50", "price_basis": "WET", "source_desc": "E2E 录入", "remark": null, "created_at": "2026-11-07 18:20:35", "updated_at": "2026-11-07 18:20:35", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"price": 830.5, "priceBasis": "WET"}', '127.0.0.1', '2026-11-07 18:20:35.606631');
INSERT INTO public.sys_operation_log VALUES (1346, 27, 26, 'sys_file', 75, 'UPLOAD', NULL, '{"fileName": "stamp-buyer-1108022034.pdf", "size": 28}', '127.0.0.1', '2026-11-07 18:20:37.3384');
INSERT INTO public.sys_operation_log VALUES (1382, 27, 26, 'biz_alert', 4, 'STATUS PROCESSING->CLOSED', '{"status": "PROCESSING"}', '{"status": "CLOSED"}', '127.0.0.1', '2026-11-07 18:20:38.542335');
INSERT INTO public.sys_operation_log VALUES (1404, 27, 26, 'biz_demand', 8, 'CREATE', NULL, '{"demandName": "E2E 全链路需求1108022236"}', '127.0.0.1', '2026-11-07 18:22:38.197252');
INSERT INTO public.sys_operation_log VALUES (1434, 27, 26, 'biz_contract', 6, 'STATUS PENDING_BUYER->PENDING_SUPPLIER', '{"status": "PENDING_BUYER"}', '{"status": "PENDING_SUPPLIER"}', '127.0.0.1', '2026-11-07 18:22:39.718597');
INSERT INTO public.sys_operation_log VALUES (1435, 27, 26, 'biz_contract', 6, 'SIGN(需方)', NULL, '{"signerName": "需方经办", "fileSha256": "4b8f3ce960bc6d4fda6aee1099f7d37530ae5a8e719e163c1f1ed1036e5f8a11"}', '127.0.0.1', '2026-11-07 18:22:39.718597');
INSERT INTO public.sys_operation_log VALUES (1470, 27, 26, 'biz_quality_check', 9, 'CREATE', NULL, '{"checkNo": "ZJ-20261108-0010", "arrivedQty": "26000", "conclusion": "ACCEPT"}', '127.0.0.1', '2026-11-07 18:22:40.851715');
INSERT INTO public.sys_operation_log VALUES (1492, NULL, NULL, 'sys_user', 35, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:27:45.318666');
INSERT INTO public.sys_operation_log VALUES (1516, 37, 36, 'biz_bargain', 15, 'STATUS PENDING->ACCEPTED', '{"status": "PENDING"}', '{"status": "ACCEPTED"}', '127.0.0.1', '2026-11-07 18:27:47.307366');
INSERT INTO public.sys_operation_log VALUES (1556, 28, 27, 'biz_waybill', 9, 'STATUS IN_TRANSIT->ARRIVED', '{"status": "IN_TRANSIT"}', '{"status": "ARRIVED"}', '127.0.0.1', '2026-11-07 18:27:48.908931');
INSERT INTO public.sys_operation_log VALUES (1557, 28, 27, 'biz_waybill', 9, 'NODE ARRIVE', NULL, '{"node": "ARRIVE"}', '127.0.0.1', '2026-11-07 18:27:48.908931');
INSERT INTO public.sys_operation_log VALUES (1088, 1, NULL, 'base_price', 1, 'CREATE', NULL, '{"varietyId": 6, "priceDate": "2026-11-08", "price": "815.50", "sourceDesc": "进口PB粉港口现货基准（E2E）"}', '127.0.0.1', '2026-11-07 17:32:22.369809');
INSERT INTO public.sys_operation_log VALUES (1110, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:34:12.537557');
INSERT INTO public.sys_operation_log VALUES (1134, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:39:34.158981');
INSERT INTO public.sys_operation_log VALUES (1162, NULL, NULL, 'ent_company', 27, 'REGISTER', NULL, '{"companyName": "测试承运物流有限公司"}', '127.0.0.1', '2026-11-07 17:42:00.206573');
INSERT INTO public.sys_operation_log VALUES (1186, 1, NULL, 'biz_alert', 1, 'STATUS PROCESSING->CLOSED', '{"status": "PROCESSING"}', '{"status": "CLOSED"}', '127.0.0.1', '2026-11-07 17:44:03.351485');
INSERT INTO public.sys_operation_log VALUES (1208, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:16:59.731858');
INSERT INTO public.sys_operation_log VALUES (1229, 27, 26, 'biz_inquiry', 4, 'CREATE', NULL, '{"quantity": "20000", "invites": [25, 29, 30]}', '127.0.0.1', '2026-11-07 18:17:02.749717');
INSERT INTO public.sys_operation_log VALUES (1265, 31, 30, 'biz_contract', 3, 'STATUS PENDING_SUPPLIER->EFFECTIVE', '{"status": "PENDING_SUPPLIER"}', '{"status": "EFFECTIVE"}', '127.0.0.1', '2026-11-07 18:17:04.514944');
INSERT INTO public.sys_operation_log VALUES (1266, 31, 30, 'biz_order', 2, 'STATUS PENDING_EFFECT->PERFORMING', '{"status": "PENDING_EFFECT"}', '{"status": "PERFORMING"}', '127.0.0.1', '2026-11-07 18:17:04.514944');
INSERT INTO public.sys_operation_log VALUES (1267, 31, 30, 'biz_contract', 3, 'SIGN(供方)', NULL, '{"signerName": "供方经办", "fileSha256": "927625f17b811ff5410a97b1712222fca33f113aaf40059f3192d2e76ff83879"}', '127.0.0.1', '2026-11-07 18:17:04.514944');
INSERT INTO public.sys_operation_log VALUES (1295, 27, 26, 'biz_settlement', 2, 'STATUS PENDING_CONFIRM_BUYER->CONFIRMED', '{"status": "PENDING_CONFIRM_BUYER"}', '{"status": "CONFIRMED"}', '127.0.0.1', '2026-11-07 18:17:05.900603');
INSERT INTO public.sys_operation_log VALUES (1317, 27, 26, 'biz_demand', 6, 'CREATE', NULL, '{"demandName": "E2E 全链路需求1108022034"}', '127.0.0.1', '2026-11-07 18:20:35.808188');
INSERT INTO public.sys_operation_log VALUES (1347, 27, 26, 'biz_contract', 4, 'STATUS PENDING_BUYER->PENDING_SUPPLIER', '{"status": "PENDING_BUYER"}', '{"status": "PENDING_SUPPLIER"}', '127.0.0.1', '2026-11-07 18:20:37.364854');
INSERT INTO public.sys_operation_log VALUES (1348, 27, 26, 'biz_contract', 4, 'SIGN(需方)', NULL, '{"signerName": "需方经办", "fileSha256": "4b8f3ce960bc6d4fda6aee1099f7d37530ae5a8e719e163c1f1ed1036e5f8a11"}', '127.0.0.1', '2026-11-07 18:20:37.364854');
INSERT INTO public.sys_operation_log VALUES (1383, 27, 26, 'biz_quality_check', 6, 'CREATE', NULL, '{"checkNo": "ZJ-20261108-0007", "arrivedQty": "26000", "conclusion": "ACCEPT"}', '127.0.0.1', '2026-11-07 18:20:38.571806');
INSERT INTO public.sys_operation_log VALUES (1405, 27, 26, 'biz_demand', 8, 'UPDATE', NULL, '{"demandName": "E2E 全链路需求1108022236"}', '127.0.0.1', '2026-11-07 18:22:38.228693');
INSERT INTO public.sys_operation_log VALUES (1436, 27, 26, 'biz_contract', 6, 'STATUS PENDING_SUPPLIER->VOID', '{"status": "PENDING_SUPPLIER"}', '{"status": "VOID"}', '127.0.0.1', '2026-11-07 18:22:39.756784');
INSERT INTO public.sys_operation_log VALUES (1437, 27, 26, 'biz_order', 4, 'STATUS PENDING_EFFECT->PENDING_CONTRACT', '{"status": "PENDING_EFFECT"}', '{"status": "PENDING_CONTRACT"}', '127.0.0.1', '2026-11-07 18:22:39.756784');
INSERT INTO public.sys_operation_log VALUES (1438, 27, 26, 'biz_contract', 6, 'VOID', NULL, '{"reason": "E2E：条款调整，作废重签"}', '127.0.0.1', '2026-11-07 18:22:39.756784');
INSERT INTO public.sys_operation_log VALUES (1471, 27, 26, 'biz_alert', 7, 'STATUS PENDING->CLOSED', '{"status": "PENDING"}', '{"status": "CLOSED"}', '127.0.0.1', '2026-11-07 18:22:40.913731');
INSERT INTO public.sys_operation_log VALUES (1493, NULL, NULL, 'sys_user', 36, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:27:45.493317');
INSERT INTO public.sys_operation_log VALUES (1517, 27, 26, 'biz_quote', 13, 'STATUS BARGAINING->WIN', '{"status": "BARGAINING"}', '{"status": "WIN"}', '127.0.0.1', '2026-11-07 18:27:47.385495');
INSERT INTO public.sys_operation_log VALUES (1518, 27, 26, 'biz_quote', 11, 'STATUS REVEALED->LOSE', '{"status": "REVEALED"}', '{"status": "LOSE"}', '127.0.0.1', '2026-11-07 18:27:47.385495');
INSERT INTO public.sys_operation_log VALUES (1519, 27, 26, 'biz_quote', 12, 'STATUS REVEALED->LOSE', '{"status": "REVEALED"}', '{"status": "LOSE"}', '127.0.0.1', '2026-11-07 18:27:47.385495');
INSERT INTO public.sys_operation_log VALUES (1520, 27, 26, 'biz_inquiry', 7, 'STATUS BARGAINING->AWARDED', '{"status": "BARGAINING"}', '{"status": "AWARDED"}', '127.0.0.1', '2026-11-07 18:27:47.385495');
INSERT INTO public.sys_operation_log VALUES (1521, 27, 26, 'biz_order', 5, 'AWARD', NULL, '{"quoteId": 13, "price": "806.00", "quantity": "20000.000"}', '127.0.0.1', '2026-11-07 18:27:47.385495');
INSERT INTO public.sys_operation_log VALUES (1558, 27, 26, 'biz_waybill', 9, 'STATUS ARRIVED->SIGNED', '{"status": "ARRIVED"}', '{"status": "SIGNED"}', '127.0.0.1', '2026-11-07 18:27:48.955761');
INSERT INTO public.sys_operation_log VALUES (1559, 27, 26, 'biz_waybill', 9, 'SIGN', NULL, '{}', '127.0.0.1', '2026-11-07 18:27:48.955761');
INSERT INTO public.sys_operation_log VALUES (1083, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:25:39.783641');
INSERT INTO public.sys_operation_log VALUES (1089, 1, NULL, 'base_price', 2, 'CREATE', NULL, '{"varietyId": 7, "priceDate": "2026-11-08", "price": "862.00", "sourceDesc": "中华混一号港口现货基准（E2E）"}', '127.0.0.1', '2026-11-07 17:32:24.452187');
INSERT INTO public.sys_operation_log VALUES (1111, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:34:14.662522');
INSERT INTO public.sys_operation_log VALUES (1135, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:39:36.278652');
INSERT INTO public.sys_operation_log VALUES (1163, 1, NULL, 'ent_company', 27, 'STATUS PENDING->APPROVED', '{"status": "PENDING"}', '{"status": "APPROVED"}', '127.0.0.1', '2026-11-07 17:42:02.334794');
INSERT INTO public.sys_operation_log VALUES (1187, 27, 26, 'biz_settlement', 1, 'CREATE', NULL, '{"settleNo": "JS-20261108-0001", "totalAmount": "15079000.00"}', '127.0.0.1', '2026-11-07 17:44:05.617624');
INSERT INTO public.sys_operation_log VALUES (1209, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:17:00.747331');
INSERT INTO public.sys_operation_log VALUES (1230, 27, 26, 'biz_inquiry', 4, 'STATUS DRAFT->SENT', '{"status": "DRAFT"}', '{"status": "SENT"}', '127.0.0.1', '2026-11-07 18:17:02.783266');
INSERT INTO public.sys_operation_log VALUES (1231, 27, 26, 'biz_demand', 4, 'STATUS SUBMITTED->INQUIRING', '{"status": "SUBMITTED"}', '{"status": "INQUIRING"}', '127.0.0.1', '2026-11-07 18:17:02.783266');
INSERT INTO public.sys_operation_log VALUES (1268, 27, 26, 'biz_logistics_plan', 2, 'CREATE', NULL, '{"orgMode": "PLATFORM", "remark": "E2E 物流"}', '127.0.0.1', '2026-11-07 18:17:04.672696');
INSERT INTO public.sys_operation_log VALUES (1296, 27, 26, 'biz_settlement', 2, 'STATUS CONFIRMED->COMPLETED', '{"status": "CONFIRMED"}', '{"status": "COMPLETED"}', '127.0.0.1', '2026-11-07 18:17:05.949105');
INSERT INTO public.sys_operation_log VALUES (1297, 27, 26, 'biz_payment', 3, 'CREATE', NULL, '{"paymentNo": "FK-20261108-0003", "amount": "16523000.0"}', '127.0.0.1', '2026-11-07 18:17:05.949105');
INSERT INTO public.sys_operation_log VALUES (1318, 27, 26, 'biz_demand', 6, 'UPDATE', NULL, '{"demandName": "E2E 全链路需求1108022034"}', '127.0.0.1', '2026-11-07 18:20:35.836348');
INSERT INTO public.sys_operation_log VALUES (1349, 27, 26, 'biz_contract', 4, 'STATUS PENDING_SUPPLIER->VOID', '{"status": "PENDING_SUPPLIER"}', '{"status": "VOID"}', '127.0.0.1', '2026-11-07 18:20:37.404098');
INSERT INTO public.sys_operation_log VALUES (1350, 27, 26, 'biz_order', 3, 'STATUS PENDING_EFFECT->PENDING_CONTRACT', '{"status": "PENDING_EFFECT"}', '{"status": "PENDING_CONTRACT"}', '127.0.0.1', '2026-11-07 18:20:37.404098');
INSERT INTO public.sys_operation_log VALUES (1351, 27, 26, 'biz_contract', 4, 'VOID', NULL, '{"reason": "E2E：条款调整，作废重签"}', '127.0.0.1', '2026-11-07 18:20:37.404098');
INSERT INTO public.sys_operation_log VALUES (1384, 27, 26, 'biz_alert', 5, 'STATUS PENDING->CLOSED', '{"status": "PENDING"}', '{"status": "CLOSED"}', '127.0.0.1', '2026-11-07 18:20:38.634138');
INSERT INTO public.sys_operation_log VALUES (1406, 27, 26, 'biz_demand', 8, 'STATUS DRAFT->SUBMITTED', '{"status": "DRAFT", "version": 1}', '{"status": "SUBMITTED", "version": 1}', '127.0.0.1', '2026-11-07 18:22:38.302952');
INSERT INTO public.sys_operation_log VALUES (1439, 27, 26, 'biz_contract', 7, 'STATUS PENDING_GENERATE->PENDING_BUYER', '{"status": "PENDING_GENERATE"}', '{"status": "PENDING_BUYER"}', '127.0.0.1', '2026-11-07 18:22:39.842852');
INSERT INTO public.sys_operation_log VALUES (1440, 27, 26, 'biz_order', 4, 'STATUS PENDING_CONTRACT->PENDING_EFFECT', '{"status": "PENDING_CONTRACT"}', '{"status": "PENDING_EFFECT"}', '127.0.0.1', '2026-11-07 18:22:39.842852');
INSERT INTO public.sys_operation_log VALUES (1441, 27, 26, 'biz_contract', 7, 'GENERATE', NULL, '{"version": 2}', '127.0.0.1', '2026-11-07 18:22:39.842852');
INSERT INTO public.sys_operation_log VALUES (1472, 27, 26, 'biz_quality_check', 10, 'CREATE', NULL, '{"checkNo": "ZJ-20261108-0011", "arrivedQty": "20500", "conclusion": "ACCEPT"}', '127.0.0.1', '2026-11-07 18:22:40.944454');
INSERT INTO public.sys_operation_log VALUES (1494, NULL, NULL, 'sys_user', 37, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:27:45.661217');
INSERT INTO public.sys_operation_log VALUES (1522, 37, 36, 'biz_order', 5, 'STATUS PENDING_CONFIRM->PENDING_CONTRACT', '{"status": "PENDING_CONFIRM"}', '{"status": "PENDING_CONTRACT"}', '127.0.0.1', '2026-11-07 18:27:47.648639');
INSERT INTO public.sys_operation_log VALUES (1560, 27, 26, 'biz_quality_check', 11, 'CREATE', NULL, '{"checkNo": "ZJ-20261108-0012", "arrivedQty": "25000", "conclusion": "ACCEPT"}', '127.0.0.1', '2026-11-07 18:27:49.094021');
INSERT INTO public.sys_operation_log VALUES (1084, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:25:49.74111');
INSERT INTO public.sys_operation_log VALUES (1090, 1, NULL, 'base_price', 1, 'UPDATE', '{"id": 1, "variety_id": 6, "price_date": "2026-11-08", "price": "815.50", "price_basis": "WET", "source_desc": "进口PB粉港口现货基准（E2E）", "remark": null, "created_at": "2026-11-07 17:32:22", "updated_at": "2026-11-07 17:32:22", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"price": "818.00", "priceBasis": null}', '127.0.0.1', '2026-11-07 17:32:26.516783');
INSERT INTO public.sys_operation_log VALUES (1112, 1, NULL, 'base_price', 1, 'UPDATE', '{"id": 1, "variety_id": 6, "price_date": "2026-11-08", "price": "818.00", "price_basis": "WET", "source_desc": null, "remark": null, "created_at": "2026-11-07 17:32:22", "updated_at": "2026-11-07 17:33:37", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"price": "815.50", "priceBasis": null}', '127.0.0.1', '2026-11-07 17:34:16.793259');
INSERT INTO public.sys_operation_log VALUES (1136, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:39:38.408653');
INSERT INTO public.sys_operation_log VALUES (1164, NULL, NULL, 'sys_user', 28, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:42:04.419967');
INSERT INTO public.sys_operation_log VALUES (1188, 26, 25, 'biz_settlement', 1, 'STATUS PENDING_CONFIRM_SUPPLIER->PENDING_CONFIRM_BUYER', '{"status": "PENDING_CONFIRM_SUPPLIER"}', '{"status": "PENDING_CONFIRM_BUYER"}', '127.0.0.1', '2026-11-07 17:44:09.938801');
INSERT INTO public.sys_operation_log VALUES (1210, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:17:00.838635');
INSERT INTO public.sys_operation_log VALUES (1232, 26, 25, 'biz_inquiry', 4, 'STATUS SENT->QUOTING', '{"status": "SENT"}', '{"status": "QUOTING"}', '127.0.0.1', '2026-11-07 18:17:02.921377');
INSERT INTO public.sys_operation_log VALUES (1233, 26, 25, 'biz_quote', 2, 'CREATE', NULL, '{"price": "818.0", "quantity": "20000"}', '127.0.0.1', '2026-11-07 18:17:02.921377');
INSERT INTO public.sys_operation_log VALUES (1269, 27, 26, 'biz_waybill', 2, 'DEVIATION', NULL, '{"deviationRate": "50.00%", "reason": "首段运力有限，剩余量由第二段补齐"}', '127.0.0.1', '2026-11-07 18:17:04.77915');
INSERT INTO public.sys_operation_log VALUES (1270, 27, 26, 'biz_waybill', 2, 'CREATE', NULL, '{"planQty": "10000", "status": "PENDING_ASSIGN"}', '127.0.0.1', '2026-11-07 18:17:04.77915');
INSERT INTO public.sys_operation_log VALUES (1298, 27, 26, 'biz_order', 2, 'STATUS PERFORMING->COMPLETED', '{"status": "PERFORMING"}', '{"status": "COMPLETED"}', '127.0.0.1', '2026-11-07 18:17:06.041757');
INSERT INTO public.sys_operation_log VALUES (1319, 27, 26, 'biz_demand', 6, 'STATUS DRAFT->SUBMITTED', '{"status": "DRAFT", "version": 1}', '{"status": "SUBMITTED", "version": 1}', '127.0.0.1', '2026-11-07 18:20:35.892106');
INSERT INTO public.sys_operation_log VALUES (1352, 27, 26, 'biz_contract', 5, 'STATUS PENDING_GENERATE->PENDING_BUYER', '{"status": "PENDING_GENERATE"}', '{"status": "PENDING_BUYER"}', '127.0.0.1', '2026-11-07 18:20:37.495568');
INSERT INTO public.sys_operation_log VALUES (1353, 27, 26, 'biz_order', 3, 'STATUS PENDING_CONTRACT->PENDING_EFFECT', '{"status": "PENDING_CONTRACT"}', '{"status": "PENDING_EFFECT"}', '127.0.0.1', '2026-11-07 18:20:37.495568');
INSERT INTO public.sys_operation_log VALUES (1354, 27, 26, 'biz_contract', 5, 'GENERATE', NULL, '{"version": 2}', '127.0.0.1', '2026-11-07 18:20:37.495568');
INSERT INTO public.sys_operation_log VALUES (1385, 27, 26, 'biz_quality_check', 7, 'CREATE', NULL, '{"checkNo": "ZJ-20261108-0008", "arrivedQty": "20500", "conclusion": "ACCEPT"}', '127.0.0.1', '2026-11-07 18:20:38.663452');
INSERT INTO public.sys_operation_log VALUES (1407, 27, 26, 'biz_demand', 8, 'STATUS SUBMITTED->WITHDRAWN', '{"status": "SUBMITTED"}', '{"status": "WITHDRAWN"}', '127.0.0.1', '2026-11-07 18:22:38.355427');
INSERT INTO public.sys_operation_log VALUES (1442, 27, 26, 'biz_contract', 7, 'STATUS PENDING_BUYER->PENDING_SUPPLIER', '{"status": "PENDING_BUYER"}', '{"status": "PENDING_SUPPLIER"}', '127.0.0.1', '2026-11-07 18:22:39.904823');
INSERT INTO public.sys_operation_log VALUES (1443, 27, 26, 'biz_contract', 7, 'SIGN(需方)', NULL, '{"signerName": "需方经办", "fileSha256": "4b8f3ce960bc6d4fda6aee1099f7d37530ae5a8e719e163c1f1ed1036e5f8a11"}', '127.0.0.1', '2026-11-07 18:22:39.904823');
INSERT INTO public.sys_operation_log VALUES (1473, 27, 26, 'biz_settlement', 4, 'CREATE', NULL, '{"settleNo": "JS-20261108-0004", "totalAmount": "16523000.00"}', '127.0.0.1', '2026-11-07 18:22:41.001419');
INSERT INTO public.sys_operation_log VALUES (1495, 1, NULL, 'base_price', 6, 'CREATE', NULL, '{"varietyId": 6, "priceDate": "2026-11-08", "price": 820.5, "priceBasis": "WET", "sourceDesc": "E2E 录入"}', '127.0.0.1', '2026-11-07 18:27:45.894652');
INSERT INTO public.sys_operation_log VALUES (1523, 27, 26, 'biz_contract', 8, 'STATUS PENDING_GENERATE->PENDING_BUYER', '{"status": "PENDING_GENERATE"}', '{"status": "PENDING_BUYER"}', '127.0.0.1', '2026-11-07 18:27:47.722347');
INSERT INTO public.sys_operation_log VALUES (1524, 27, 26, 'biz_order', 5, 'STATUS PENDING_CONTRACT->PENDING_EFFECT', '{"status": "PENDING_CONTRACT"}', '{"status": "PENDING_EFFECT"}', '127.0.0.1', '2026-11-07 18:27:47.722347');
INSERT INTO public.sys_operation_log VALUES (1525, 27, 26, 'biz_contract', 8, 'GENERATE', NULL, '{"version": 1}', '127.0.0.1', '2026-11-07 18:27:47.722347');
INSERT INTO public.sys_operation_log VALUES (1561, 27, 26, 'biz_alert', 8, 'STATUS PENDING->PROCESSING', '{"status": "PENDING"}', '{"status": "PROCESSING"}', '127.0.0.1', '2026-11-07 18:27:49.158543');
INSERT INTO public.sys_operation_log VALUES (1091, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:32:57.976449');
INSERT INTO public.sys_operation_log VALUES (1113, 1, NULL, 'base_price', 2, 'UPDATE', '{"id": 2, "variety_id": 7, "price_date": "2026-11-08", "price": "862.00", "price_basis": "WET", "source_desc": "中华混一号港口现货基准（E2E）", "remark": null, "created_at": "2026-11-07 17:32:24", "updated_at": "2026-11-07 17:33:35", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"price": "862.00", "priceBasis": null}', '127.0.0.1', '2026-11-07 17:34:18.869128');
INSERT INTO public.sys_operation_log VALUES (1137, 27, 26, 'biz_bargain', 2, 'CREATE', NULL, '{"quoteId": 1, "roundNo": 2, "initiator": "BUYER"}', '127.0.0.1', '2026-11-07 17:39:40.74008');
INSERT INTO public.sys_operation_log VALUES (1165, 27, 26, 'biz_inquiry', 3, 'CREATE', NULL, '{"quantity": "18000", "invites": [26]}', '127.0.0.1', '2026-11-07 17:42:07.137765');
INSERT INTO public.sys_operation_log VALUES (1189, 27, 26, 'biz_settlement', 1, 'STATUS PENDING_CONFIRM_BUYER->CONFIRMED', '{"status": "PENDING_CONFIRM_BUYER"}', '{"status": "CONFIRMED"}', '127.0.0.1', '2026-11-07 17:44:12.235342');
INSERT INTO public.sys_operation_log VALUES (1211, NULL, NULL, 'sys_user', 28, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:17:00.932423');
INSERT INTO public.sys_operation_log VALUES (1234, 30, 29, 'biz_quote', 3, 'CREATE', NULL, '{"price": "815.0", "quantity": "20000"}', '127.0.0.1', '2026-11-07 18:17:03.028827');
INSERT INTO public.sys_operation_log VALUES (1271, 27, 26, 'biz_waybill', 2, 'ASSIGN', NULL, '{"carrierId": 27}', '127.0.0.1', '2026-11-07 18:17:04.827457');
INSERT INTO public.sys_operation_log VALUES (1299, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:18:29.603283');
INSERT INTO public.sys_operation_log VALUES (1320, 27, 26, 'biz_demand', 6, 'STATUS SUBMITTED->WITHDRAWN', '{"status": "SUBMITTED"}', '{"status": "WITHDRAWN"}', '127.0.0.1', '2026-11-07 18:20:35.957157');
INSERT INTO public.sys_operation_log VALUES (1355, 27, 26, 'biz_contract', 5, 'STATUS PENDING_BUYER->PENDING_SUPPLIER', '{"status": "PENDING_BUYER"}', '{"status": "PENDING_SUPPLIER"}', '127.0.0.1', '2026-11-07 18:20:37.576528');
INSERT INTO public.sys_operation_log VALUES (1356, 27, 26, 'biz_contract', 5, 'SIGN(需方)', NULL, '{"signerName": "需方经办", "fileSha256": "4b8f3ce960bc6d4fda6aee1099f7d37530ae5a8e719e163c1f1ed1036e5f8a11"}', '127.0.0.1', '2026-11-07 18:20:37.576528');
INSERT INTO public.sys_operation_log VALUES (1386, 27, 26, 'biz_settlement', 3, 'CREATE', NULL, '{"settleNo": "JS-20261108-0003", "totalAmount": "16523000.00"}', '127.0.0.1', '2026-11-07 18:20:38.729864');
INSERT INTO public.sys_operation_log VALUES (1408, 27, 26, 'biz_demand', 8, 'STATUS WITHDRAWN->SUBMITTED', '{"status": "WITHDRAWN", "version": 1}', '{"status": "SUBMITTED", "version": 2}', '127.0.0.1', '2026-11-07 18:22:38.402092');
INSERT INTO public.sys_operation_log VALUES (1444, 31, 30, 'sys_file', 80, 'UPLOAD', NULL, '{"fileName": "stamp-supplier-1108022236.png", "size": 28}', '127.0.0.1', '2026-11-07 18:22:39.941419');
INSERT INTO public.sys_operation_log VALUES (1474, 31, 30, 'biz_settlement', 4, 'STATUS PENDING_CONFIRM_SUPPLIER->PENDING_CONFIRM_BUYER', '{"status": "PENDING_CONFIRM_SUPPLIER"}', '{"status": "PENDING_CONFIRM_BUYER"}', '127.0.0.1', '2026-11-07 18:22:41.067211');
INSERT INTO public.sys_operation_log VALUES (1496, 1, NULL, 'base_price', 6, 'UPDATE', '{"id": 6, "variety_id": 6, "price_date": "2026-11-08", "price": "820.50", "price_basis": "WET", "source_desc": "E2E 录入", "remark": null, "created_at": "2026-11-07 18:27:45", "updated_at": "2026-11-07 18:27:45", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"price": 830.5, "priceBasis": "WET"}', '127.0.0.1', '2026-11-07 18:27:45.939382');
INSERT INTO public.sys_operation_log VALUES (1526, 27, 26, 'sys_file', 85, 'UPLOAD', NULL, '{"fileName": "stamp-buyer-1108022743.pdf", "size": 28}', '127.0.0.1', '2026-11-07 18:27:47.868885');
INSERT INTO public.sys_operation_log VALUES (1562, 27, 26, 'biz_alert', 8, 'STATUS PROCESSING->CLOSED', '{"status": "PROCESSING"}', '{"status": "CLOSED"}', '127.0.0.1', '2026-11-07 18:27:49.24955');
INSERT INTO public.sys_operation_log VALUES (1092, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:33:00.091764');
INSERT INTO public.sys_operation_log VALUES (1114, 1, NULL, 'base_price', 1, 'UPDATE', '{"id": 1, "variety_id": 6, "price_date": "2026-11-08", "price": "815.50", "price_basis": "WET", "source_desc": "进口PB粉港口现货基准（E2E）", "remark": null, "created_at": "2026-11-07 17:32:22", "updated_at": "2026-11-07 17:34:16", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"price": "818.00", "priceBasis": null}', '127.0.0.1', '2026-11-07 17:34:20.951128');
INSERT INTO public.sys_operation_log VALUES (1138, 27, 26, 'biz_bargain', 3, 'CREATE', NULL, '{"quoteId": 1, "roundNo": 3, "initiator": "BUYER"}', '127.0.0.1', '2026-11-07 17:39:42.825832');
INSERT INTO public.sys_operation_log VALUES (1166, 27, 26, 'biz_inquiry', 3, 'STATUS DRAFT->SENT', '{"status": "DRAFT"}', '{"status": "SENT"}', '127.0.0.1', '2026-11-07 17:42:09.220084');
INSERT INTO public.sys_operation_log VALUES (1190, 27, 26, 'biz_settlement', 1, 'STATUS CONFIRMED->COMPLETED', '{"status": "CONFIRMED"}', '{"status": "COMPLETED"}', '127.0.0.1', '2026-11-07 17:44:14.518791');
INSERT INTO public.sys_operation_log VALUES (1191, 27, 26, 'biz_payment', 1, 'CREATE', NULL, '{"paymentNo": "FK-20261108-0001", "amount": "15079000.0"}', '127.0.0.1', '2026-11-07 17:44:14.518791');
INSERT INTO public.sys_operation_log VALUES (1212, NULL, NULL, 'ent_company', 28, 'REGISTER', NULL, '{"companyName": "E2E钢厂二1108021659"}', '127.0.0.1', '2026-11-07 18:17:01.071885');
INSERT INTO public.sys_operation_log VALUES (1235, 31, 30, 'biz_quote', 4, 'CREATE', NULL, '{"price": "812.0", "quantity": "20000"}', '127.0.0.1', '2026-11-07 18:17:03.103206');
INSERT INTO public.sys_operation_log VALUES (1272, 28, 27, 'biz_waybill', 2, 'STATUS PENDING_ACCEPT->PENDING_DEPART', '{"status": "PENDING_ACCEPT"}', '{"status": "PENDING_DEPART"}', '127.0.0.1', '2026-11-07 18:17:04.857844');
INSERT INTO public.sys_operation_log VALUES (1300, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:18:30.014477');
INSERT INTO public.sys_operation_log VALUES (1321, 27, 26, 'biz_demand', 6, 'STATUS WITHDRAWN->SUBMITTED', '{"status": "WITHDRAWN", "version": 1}', '{"status": "SUBMITTED", "version": 2}', '127.0.0.1', '2026-11-07 18:20:36.009324');
INSERT INTO public.sys_operation_log VALUES (1357, 31, 30, 'sys_file', 76, 'UPLOAD', NULL, '{"fileName": "stamp-supplier-1108022034.png", "size": 28}', '127.0.0.1', '2026-11-07 18:20:37.622314');
INSERT INTO public.sys_operation_log VALUES (1387, 31, 30, 'biz_settlement', 3, 'STATUS PENDING_CONFIRM_SUPPLIER->PENDING_CONFIRM_BUYER', '{"status": "PENDING_CONFIRM_SUPPLIER"}', '{"status": "PENDING_CONFIRM_BUYER"}', '127.0.0.1', '2026-11-07 18:20:38.787926');
INSERT INTO public.sys_operation_log VALUES (1409, 27, 26, 'biz_inquiry', 6, 'CREATE', NULL, '{"quantity": "20000", "invites": [25, 29, 30]}', '127.0.0.1', '2026-11-07 18:22:38.491773');
INSERT INTO public.sys_operation_log VALUES (1445, 31, 30, 'biz_contract', 7, 'STATUS PENDING_SUPPLIER->EFFECTIVE', '{"status": "PENDING_SUPPLIER"}', '{"status": "EFFECTIVE"}', '127.0.0.1', '2026-11-07 18:22:39.968358');
INSERT INTO public.sys_operation_log VALUES (1446, 31, 30, 'biz_order', 4, 'STATUS PENDING_EFFECT->PERFORMING', '{"status": "PENDING_EFFECT"}', '{"status": "PERFORMING"}', '127.0.0.1', '2026-11-07 18:22:39.968358');
INSERT INTO public.sys_operation_log VALUES (1447, 31, 30, 'biz_contract', 7, 'SIGN(供方)', NULL, '{"signerName": "供方经办", "fileSha256": "927625f17b811ff5410a97b1712222fca33f113aaf40059f3192d2e76ff83879"}', '127.0.0.1', '2026-11-07 18:22:39.968358');
INSERT INTO public.sys_operation_log VALUES (1475, 27, 26, 'biz_settlement', 4, 'STATUS PENDING_CONFIRM_BUYER->CONFIRMED', '{"status": "PENDING_CONFIRM_BUYER"}', '{"status": "CONFIRMED"}', '127.0.0.1', '2026-11-07 18:22:41.125612');
INSERT INTO public.sys_operation_log VALUES (1497, 27, 26, 'biz_demand', 10, 'CREATE', NULL, '{"demandName": "E2E 全链路需求1108022743"}', '127.0.0.1', '2026-11-07 18:27:46.105074');
INSERT INTO public.sys_operation_log VALUES (1527, 27, 26, 'biz_contract', 8, 'STATUS PENDING_BUYER->PENDING_SUPPLIER', '{"status": "PENDING_BUYER"}', '{"status": "PENDING_SUPPLIER"}', '127.0.0.1', '2026-11-07 18:27:47.913185');
INSERT INTO public.sys_operation_log VALUES (1528, 27, 26, 'biz_contract', 8, 'SIGN(需方)', NULL, '{"signerName": "需方经办", "fileSha256": "4b8f3ce960bc6d4fda6aee1099f7d37530ae5a8e719e163c1f1ed1036e5f8a11"}', '127.0.0.1', '2026-11-07 18:27:47.913185');
INSERT INTO public.sys_operation_log VALUES (1563, 27, 26, 'biz_quality_check', 12, 'CREATE', NULL, '{"checkNo": "ZJ-20261108-0013", "arrivedQty": "26000", "conclusion": "ACCEPT"}', '127.0.0.1', '2026-11-07 18:27:49.297659');
INSERT INTO public.sys_operation_log VALUES (1093, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:33:02.220298');
INSERT INTO public.sys_operation_log VALUES (1115, 27, 26, 'biz_demand', 2, 'CREATE', NULL, '{"demandName": "11月PB粉与中华混一号采购"}', '127.0.0.1', '2026-11-07 17:34:25.102653');
INSERT INTO public.sys_operation_log VALUES (1139, 27, 26, 'biz_bargain', 1, 'STATUS PENDING->ACCEPTED', '{"status": "PENDING"}', '{"status": "ACCEPTED"}', '127.0.0.1', '2026-11-07 17:39:44.905779');
INSERT INTO public.sys_operation_log VALUES (1192, 27, 26, 'biz_payment', 2, 'CREATE', NULL, '{"paymentNo": "FK-20261108-0002", "amount": "99999999.0"}', '127.0.0.1', '2026-11-07 17:44:16.785057');
INSERT INTO public.sys_operation_log VALUES (1213, NULL, NULL, 'ent_company', 29, 'REGISTER', NULL, '{"companyName": "E2E补位供应商11108021659"}', '127.0.0.1', '2026-11-07 18:17:01.294796');
INSERT INTO public.sys_operation_log VALUES (1236, 27, 26, 'biz_inquiry', 4, 'STATUS QUOTING->CLOSED', '{"status": "QUOTING"}', '{"status": "CLOSED"}', '127.0.0.1', '2026-11-07 18:17:03.333859');
INSERT INTO public.sys_operation_log VALUES (1273, 28, 27, 'biz_waybill', 2, 'STATUS PENDING_DEPART->IN_TRANSIT', '{"status": "PENDING_DEPART"}', '{"status": "IN_TRANSIT"}', '127.0.0.1', '2026-11-07 18:17:04.903884');
INSERT INTO public.sys_operation_log VALUES (1274, 28, 27, 'biz_waybill', 2, 'NODE DEPART', NULL, '{"node": "DEPART", "actualQty": 10000}', '127.0.0.1', '2026-11-07 18:17:04.903884');
INSERT INTO public.sys_operation_log VALUES (1301, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:18:30.103776');
INSERT INTO public.sys_operation_log VALUES (1322, 27, 26, 'biz_inquiry', 5, 'CREATE', NULL, '{"quantity": "20000", "invites": [25, 29, 30]}', '127.0.0.1', '2026-11-07 18:20:36.092953');
INSERT INTO public.sys_operation_log VALUES (1358, 31, 30, 'biz_contract', 5, 'STATUS PENDING_SUPPLIER->EFFECTIVE', '{"status": "PENDING_SUPPLIER"}', '{"status": "EFFECTIVE"}', '127.0.0.1', '2026-11-07 18:20:37.669415');
INSERT INTO public.sys_operation_log VALUES (1359, 31, 30, 'biz_order', 3, 'STATUS PENDING_EFFECT->PERFORMING', '{"status": "PENDING_EFFECT"}', '{"status": "PERFORMING"}', '127.0.0.1', '2026-11-07 18:20:37.669415');
INSERT INTO public.sys_operation_log VALUES (1360, 31, 30, 'biz_contract', 5, 'SIGN(供方)', NULL, '{"signerName": "供方经办", "fileSha256": "927625f17b811ff5410a97b1712222fca33f113aaf40059f3192d2e76ff83879"}', '127.0.0.1', '2026-11-07 18:20:37.669415');
INSERT INTO public.sys_operation_log VALUES (1388, 27, 26, 'biz_settlement', 3, 'STATUS PENDING_CONFIRM_BUYER->CONFIRMED', '{"status": "PENDING_CONFIRM_BUYER"}', '{"status": "CONFIRMED"}', '127.0.0.1', '2026-11-07 18:20:38.861657');
INSERT INTO public.sys_operation_log VALUES (1410, 27, 26, 'biz_inquiry', 6, 'STATUS DRAFT->SENT', '{"status": "DRAFT"}', '{"status": "SENT"}', '127.0.0.1', '2026-11-07 18:22:38.533412');
INSERT INTO public.sys_operation_log VALUES (1411, 27, 26, 'biz_demand', 8, 'STATUS SUBMITTED->INQUIRING', '{"status": "SUBMITTED"}', '{"status": "INQUIRING"}', '127.0.0.1', '2026-11-07 18:22:38.533412');
INSERT INTO public.sys_operation_log VALUES (1448, 27, 26, 'biz_logistics_plan', 4, 'CREATE', NULL, '{"orgMode": "PLATFORM", "remark": "E2E 物流"}', '127.0.0.1', '2026-11-07 18:22:40.108371');
INSERT INTO public.sys_operation_log VALUES (1476, 27, 26, 'biz_settlement', 4, 'STATUS CONFIRMED->COMPLETED', '{"status": "CONFIRMED"}', '{"status": "COMPLETED"}', '127.0.0.1', '2026-11-07 18:22:41.176427');
INSERT INTO public.sys_operation_log VALUES (1477, 27, 26, 'biz_payment', 5, 'CREATE', NULL, '{"paymentNo": "FK-20261108-0005", "amount": "16523000.0"}', '127.0.0.1', '2026-11-07 18:22:41.176427');
INSERT INTO public.sys_operation_log VALUES (1498, 27, 26, 'biz_demand', 10, 'UPDATE', NULL, '{"demandName": "E2E 全链路需求1108022743"}', '127.0.0.1', '2026-11-07 18:27:46.140318');
INSERT INTO public.sys_operation_log VALUES (1529, 27, 26, 'biz_contract', 8, 'STATUS PENDING_SUPPLIER->VOID', '{"status": "PENDING_SUPPLIER"}', '{"status": "VOID"}', '127.0.0.1', '2026-11-07 18:27:47.959735');
INSERT INTO public.sys_operation_log VALUES (1530, 27, 26, 'biz_order', 5, 'STATUS PENDING_EFFECT->PENDING_CONTRACT', '{"status": "PENDING_EFFECT"}', '{"status": "PENDING_CONTRACT"}', '127.0.0.1', '2026-11-07 18:27:47.959735');
INSERT INTO public.sys_operation_log VALUES (1531, 27, 26, 'biz_contract', 8, 'VOID', NULL, '{"reason": "E2E：条款调整，作废重签"}', '127.0.0.1', '2026-11-07 18:27:47.959735');
INSERT INTO public.sys_operation_log VALUES (1564, 27, 26, 'biz_alert', 9, 'STATUS PENDING->CLOSED', '{"status": "PENDING"}', '{"status": "CLOSED"}', '127.0.0.1', '2026-11-07 18:27:49.374391');
INSERT INTO public.sys_operation_log VALUES (1094, 1, NULL, 'base_price', 1, 'UPDATE', '{"id": 1, "variety_id": 6, "price_date": "2026-11-08", "price": "818.00", "price_basis": "WET", "source_desc": null, "remark": null, "created_at": "2026-11-07 17:32:22", "updated_at": "2026-11-07 17:32:26", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"price": "815.50", "priceBasis": null}', '127.0.0.1', '2026-11-07 17:33:04.343198');
INSERT INTO public.sys_operation_log VALUES (1116, 27, 26, 'biz_demand', 2, 'UPDATE', NULL, '{"demandName": "11月PB粉与中华混一号采购(修订)"}', '127.0.0.1', '2026-11-07 17:34:27.172642');
INSERT INTO public.sys_operation_log VALUES (1140, 27, 26, 'biz_quote', 1, 'STATUS BARGAINING->WIN', '{"status": "BARGAINING"}', '{"status": "WIN"}', '127.0.0.1', '2026-11-07 17:39:51.307909');
INSERT INTO public.sys_operation_log VALUES (1141, 27, 26, 'biz_inquiry', 2, 'STATUS BARGAINING->AWARDED', '{"status": "BARGAINING"}', '{"status": "AWARDED"}', '127.0.0.1', '2026-11-07 17:39:51.307909');
INSERT INTO public.sys_operation_log VALUES (1142, 27, 26, 'biz_order', 1, 'AWARD', NULL, '{"quoteId": 1, "price": "838.00", "quantity": "20000.000"}', '127.0.0.1', '2026-11-07 17:39:51.307909');
INSERT INTO public.sys_operation_log VALUES (1168, 27, 26, 'biz_waybill', 1, 'ASSIGN', NULL, '{"carrierId": 27}', '127.0.0.1', '2026-11-07 17:42:13.76952');
INSERT INTO public.sys_operation_log VALUES (1193, 27, 26, 'biz_order', 1, 'STATUS PERFORMING->COMPLETED', '{"status": "PERFORMING"}', '{"status": "COMPLETED"}', '127.0.0.1', '2026-11-07 17:44:19.053986');
INSERT INTO public.sys_operation_log VALUES (1214, NULL, NULL, 'ent_company', 30, 'REGISTER', NULL, '{"companyName": "E2E补位供应商21108021659"}', '127.0.0.1', '2026-11-07 18:17:01.435861');
INSERT INTO public.sys_operation_log VALUES (1237, 27, 26, 'biz_inquiry', 4, 'STATUS CLOSED->BARGAINING', '{"status": "CLOSED"}', '{"status": "BARGAINING"}', '127.0.0.1', '2026-11-07 18:17:03.387075');
INSERT INTO public.sys_operation_log VALUES (1238, 27, 26, 'biz_bargain', 4, 'CREATE', NULL, '{"quoteId": 4, "roundNo": 1, "initiator": "BUYER"}', '127.0.0.1', '2026-11-07 18:17:03.387075');
INSERT INTO public.sys_operation_log VALUES (1275, 28, 27, 'biz_waybill', 2, 'STATUS IN_TRANSIT->ARRIVED', '{"status": "IN_TRANSIT"}', '{"status": "ARRIVED"}', '127.0.0.1', '2026-11-07 18:17:04.934611');
INSERT INTO public.sys_operation_log VALUES (1276, 28, 27, 'biz_waybill', 2, 'NODE ARRIVE', NULL, '{"node": "ARRIVE"}', '127.0.0.1', '2026-11-07 18:17:04.934611');
INSERT INTO public.sys_operation_log VALUES (1302, NULL, NULL, 'sys_user', 28, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:18:30.201549');
INSERT INTO public.sys_operation_log VALUES (1323, 27, 26, 'biz_inquiry', 5, 'STATUS DRAFT->SENT', '{"status": "DRAFT"}', '{"status": "SENT"}', '127.0.0.1', '2026-11-07 18:20:36.133095');
INSERT INTO public.sys_operation_log VALUES (1324, 27, 26, 'biz_demand', 6, 'STATUS SUBMITTED->INQUIRING', '{"status": "SUBMITTED"}', '{"status": "INQUIRING"}', '127.0.0.1', '2026-11-07 18:20:36.133095');
INSERT INTO public.sys_operation_log VALUES (1361, 27, 26, 'biz_logistics_plan', 3, 'CREATE', NULL, '{"orgMode": "PLATFORM", "remark": "E2E 物流"}', '127.0.0.1', '2026-11-07 18:20:37.81056');
INSERT INTO public.sys_operation_log VALUES (1389, 27, 26, 'biz_settlement', 3, 'STATUS CONFIRMED->COMPLETED', '{"status": "CONFIRMED"}', '{"status": "COMPLETED"}', '127.0.0.1', '2026-11-07 18:20:38.907313');
INSERT INTO public.sys_operation_log VALUES (1390, 27, 26, 'biz_payment', 4, 'CREATE', NULL, '{"paymentNo": "FK-20261108-0004", "amount": "16523000.0"}', '127.0.0.1', '2026-11-07 18:20:38.907313');
INSERT INTO public.sys_operation_log VALUES (1412, 26, 25, 'biz_inquiry', 6, 'STATUS SENT->QUOTING', '{"status": "SENT"}', '{"status": "QUOTING"}', '127.0.0.1', '2026-11-07 18:22:38.655679');
INSERT INTO public.sys_operation_log VALUES (1413, 26, 25, 'biz_quote', 8, 'CREATE', NULL, '{"price": "818.0", "quantity": "20000"}', '127.0.0.1', '2026-11-07 18:22:38.655679');
INSERT INTO public.sys_operation_log VALUES (1449, 27, 26, 'biz_waybill', 6, 'DEVIATION', NULL, '{"deviationRate": "50.00%", "reason": "首段运力有限，剩余量由第二段补齐"}', '127.0.0.1', '2026-11-07 18:22:40.1958');
INSERT INTO public.sys_operation_log VALUES (1450, 27, 26, 'biz_waybill', 6, 'CREATE', NULL, '{"planQty": "10000", "status": "PENDING_ASSIGN"}', '127.0.0.1', '2026-11-07 18:22:40.1958');
INSERT INTO public.sys_operation_log VALUES (1478, 27, 26, 'biz_order', 4, 'STATUS PERFORMING->COMPLETED', '{"status": "PERFORMING"}', '{"status": "COMPLETED"}', '127.0.0.1', '2026-11-07 18:22:41.243743');
INSERT INTO public.sys_operation_log VALUES (1499, 27, 26, 'biz_demand', 10, 'STATUS DRAFT->SUBMITTED', '{"status": "DRAFT", "version": 1}', '{"status": "SUBMITTED", "version": 1}', '127.0.0.1', '2026-11-07 18:27:46.219574');
INSERT INTO public.sys_operation_log VALUES (1532, 27, 26, 'biz_contract', 9, 'STATUS PENDING_GENERATE->PENDING_BUYER', '{"status": "PENDING_GENERATE"}', '{"status": "PENDING_BUYER"}', '127.0.0.1', '2026-11-07 18:27:48.025156');
INSERT INTO public.sys_operation_log VALUES (1533, 27, 26, 'biz_order', 5, 'STATUS PENDING_CONTRACT->PENDING_EFFECT', '{"status": "PENDING_CONTRACT"}', '{"status": "PENDING_EFFECT"}', '127.0.0.1', '2026-11-07 18:27:48.025156');
INSERT INTO public.sys_operation_log VALUES (1534, 27, 26, 'biz_contract', 9, 'GENERATE', NULL, '{"version": 2}', '127.0.0.1', '2026-11-07 18:27:48.025156');
INSERT INTO public.sys_operation_log VALUES (1565, 27, 26, 'biz_quality_check', 13, 'CREATE', NULL, '{"checkNo": "ZJ-20261108-0014", "arrivedQty": "20500", "conclusion": "ACCEPT"}', '127.0.0.1', '2026-11-07 18:27:49.42094');
INSERT INTO public.sys_operation_log VALUES (1095, 1, NULL, 'base_price', 2, 'UPDATE', '{"id": 2, "variety_id": 7, "price_date": "2026-11-08", "price": "862.00", "price_basis": "WET", "source_desc": "中华混一号港口现货基准（E2E）", "remark": null, "created_at": "2026-11-07 17:32:24", "updated_at": "2026-11-07 17:32:24", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"price": "862.00", "priceBasis": null}', '127.0.0.1', '2026-11-07 17:33:06.424827');
INSERT INTO public.sys_operation_log VALUES (1117, 27, 26, 'biz_demand', 2, 'STATUS DRAFT->SUBMITTED', '{"status": "DRAFT", "version": 1}', '{"status": "SUBMITTED", "version": 1}', '127.0.0.1', '2026-11-07 17:34:29.254139');
INSERT INTO public.sys_operation_log VALUES (1143, 26, 25, 'biz_order', 1, 'STATUS PENDING_CONFIRM->PENDING_CONTRACT', '{"status": "PENDING_CONFIRM"}', '{"status": "PENDING_CONTRACT"}', '127.0.0.1', '2026-11-07 17:39:55.652188');
INSERT INTO public.sys_operation_log VALUES (1169, 28, 27, 'biz_waybill', 1, 'STATUS PENDING_ACCEPT->PENDING_DEPART', '{"status": "PENDING_ACCEPT"}', '{"status": "PENDING_DEPART"}', '127.0.0.1', '2026-11-07 17:42:20.182776');
INSERT INTO public.sys_operation_log VALUES (1194, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:44:37.32451');
INSERT INTO public.sys_operation_log VALUES (1215, 1, NULL, 'ent_company', 28, 'STATUS PENDING->APPROVED', '{"status": "PENDING"}', '{"status": "APPROVED"}', '127.0.0.1', '2026-11-07 18:17:01.670454');
INSERT INTO public.sys_operation_log VALUES (1239, 31, 30, 'biz_bargain', 4, 'STATUS PENDING->ACCEPTED', '{"status": "PENDING"}', '{"status": "ACCEPTED"}', '127.0.0.1', '2026-11-07 18:17:03.451259');
INSERT INTO public.sys_operation_log VALUES (1277, 27, 26, 'biz_waybill', 2, 'STATUS ARRIVED->SIGNED', '{"status": "ARRIVED"}', '{"status": "SIGNED"}', '127.0.0.1', '2026-11-07 18:17:05.005101');
INSERT INTO public.sys_operation_log VALUES (1278, 27, 26, 'biz_waybill', 2, 'SIGN', NULL, '{}', '127.0.0.1', '2026-11-07 18:17:05.005101');
INSERT INTO public.sys_operation_log VALUES (1303, NULL, NULL, 'ent_company', 31, 'REGISTER', NULL, '{"companyName": "E2E钢厂二1108021829"}', '127.0.0.1', '2026-11-07 18:18:30.328427');
INSERT INTO public.sys_operation_log VALUES (1325, 26, 25, 'biz_inquiry', 5, 'STATUS SENT->QUOTING', '{"status": "SENT"}', '{"status": "QUOTING"}', '127.0.0.1', '2026-11-07 18:20:36.242074');
INSERT INTO public.sys_operation_log VALUES (1326, 26, 25, 'biz_quote', 5, 'CREATE', NULL, '{"price": "818.0", "quantity": "20000"}', '127.0.0.1', '2026-11-07 18:20:36.242074');
INSERT INTO public.sys_operation_log VALUES (1362, 27, 26, 'biz_waybill', 4, 'DEVIATION', NULL, '{"deviationRate": "50.00%", "reason": "首段运力有限，剩余量由第二段补齐"}', '127.0.0.1', '2026-11-07 18:20:37.897708');
INSERT INTO public.sys_operation_log VALUES (1363, 27, 26, 'biz_waybill', 4, 'CREATE', NULL, '{"planQty": "10000", "status": "PENDING_ASSIGN"}', '127.0.0.1', '2026-11-07 18:20:37.897708');
INSERT INTO public.sys_operation_log VALUES (1391, 27, 26, 'biz_order', 3, 'STATUS PERFORMING->COMPLETED', '{"status": "PERFORMING"}', '{"status": "COMPLETED"}', '127.0.0.1', '2026-11-07 18:20:38.97097');
INSERT INTO public.sys_operation_log VALUES (1414, 30, 29, 'biz_quote', 9, 'CREATE', NULL, '{"price": "815.0", "quantity": "20000"}', '127.0.0.1', '2026-11-07 18:22:38.721738');
INSERT INTO public.sys_operation_log VALUES (1451, 27, 26, 'biz_waybill', 6, 'ASSIGN', NULL, '{"carrierId": 27}', '127.0.0.1', '2026-11-07 18:22:40.235685');
INSERT INTO public.sys_operation_log VALUES (1479, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:25:19.034108');
INSERT INTO public.sys_operation_log VALUES (1500, 27, 26, 'biz_demand', 10, 'STATUS SUBMITTED->WITHDRAWN', '{"status": "SUBMITTED"}', '{"status": "WITHDRAWN"}', '127.0.0.1', '2026-11-07 18:27:46.314472');
INSERT INTO public.sys_operation_log VALUES (1535, 27, 26, 'biz_contract', 9, 'STATUS PENDING_BUYER->PENDING_SUPPLIER', '{"status": "PENDING_BUYER"}', '{"status": "PENDING_SUPPLIER"}', '127.0.0.1', '2026-11-07 18:27:48.1102');
INSERT INTO public.sys_operation_log VALUES (1536, 27, 26, 'biz_contract', 9, 'SIGN(需方)', NULL, '{"signerName": "需方经办", "fileSha256": "4b8f3ce960bc6d4fda6aee1099f7d37530ae5a8e719e163c1f1ed1036e5f8a11"}', '127.0.0.1', '2026-11-07 18:27:48.1102');
INSERT INTO public.sys_operation_log VALUES (1566, 27, 26, 'biz_settlement', 5, 'CREATE', NULL, '{"settleNo": "JS-20261108-0005", "totalAmount": "16523000.00"}', '127.0.0.1', '2026-11-07 18:27:49.478526');
INSERT INTO public.sys_operation_log VALUES (1096, 1, NULL, 'base_price', 1, 'UPDATE', '{"id": 1, "variety_id": 6, "price_date": "2026-11-08", "price": "815.50", "price_basis": "WET", "source_desc": "进口PB粉港口现货基准（E2E）", "remark": null, "created_at": "2026-11-07 17:32:22", "updated_at": "2026-11-07 17:33:04", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"price": "818.00", "priceBasis": null}', '127.0.0.1', '2026-11-07 17:33:08.492897');
INSERT INTO public.sys_operation_log VALUES (1118, 27, 26, 'biz_inquiry', 2, 'CREATE', NULL, '{"quantity": "20000", "invites": [25]}', '127.0.0.1', '2026-11-07 17:34:35.459307');
INSERT INTO public.sys_operation_log VALUES (1144, 27, 26, 'biz_contract', 1, 'STATUS PENDING_GENERATE->PENDING_BUYER', '{"status": "PENDING_GENERATE"}', '{"status": "PENDING_BUYER"}', '127.0.0.1', '2026-11-07 17:40:00.005255');
INSERT INTO public.sys_operation_log VALUES (1145, 27, 26, 'biz_order', 1, 'STATUS PENDING_CONTRACT->PENDING_EFFECT', '{"status": "PENDING_CONTRACT"}', '{"status": "PENDING_EFFECT"}', '127.0.0.1', '2026-11-07 17:40:00.005255');
INSERT INTO public.sys_operation_log VALUES (1146, 27, 26, 'biz_contract', 1, 'GENERATE', NULL, '{"version": 1}', '127.0.0.1', '2026-11-07 17:40:00.005255');
INSERT INTO public.sys_operation_log VALUES (1170, 28, 27, 'biz_waybill', 1, 'STATUS PENDING_DEPART->IN_TRANSIT', '{"status": "PENDING_DEPART"}', '{"status": "IN_TRANSIT"}', '127.0.0.1', '2026-11-07 17:42:22.248841');
INSERT INTO public.sys_operation_log VALUES (1171, 28, 27, 'biz_waybill', 1, 'NODE DEPART', NULL, '{"node": "DEPART", "actualQty": 20000, "nodeTime": "2026-11-08 00:42:20", "remark": "港发"}', '127.0.0.1', '2026-11-07 17:42:22.248841');
INSERT INTO public.sys_operation_log VALUES (1195, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:44:39.448862');
INSERT INTO public.sys_operation_log VALUES (1216, 1, NULL, 'ent_company', 29, 'STATUS PENDING->APPROVED', '{"status": "PENDING"}', '{"status": "APPROVED"}', '127.0.0.1', '2026-11-07 18:17:01.700288');
INSERT INTO public.sys_operation_log VALUES (1240, 27, 26, 'biz_bargain', 5, 'CREATE', NULL, '{"quoteId": 4, "roundNo": 2, "initiator": "BUYER"}', '127.0.0.1', '2026-11-07 18:17:03.482033');
INSERT INTO public.sys_operation_log VALUES (1279, 27, 26, 'biz_waybill', 3, 'CREATE', NULL, '{"planQty": "10000", "status": "PENDING_ACCEPT"}', '127.0.0.1', '2026-11-07 18:17:05.074467');
INSERT INTO public.sys_operation_log VALUES (1304, 1, NULL, 'ent_company', 31, 'STATUS PENDING->APPROVED', '{"status": "PENDING"}', '{"status": "APPROVED"}', '127.0.0.1', '2026-11-07 18:18:30.666258');
INSERT INTO public.sys_operation_log VALUES (1327, 30, 29, 'biz_quote', 6, 'CREATE', NULL, '{"price": "815.0", "quantity": "20000"}', '127.0.0.1', '2026-11-07 18:20:36.317342');
INSERT INTO public.sys_operation_log VALUES (1364, 27, 26, 'biz_waybill', 4, 'ASSIGN', NULL, '{"carrierId": 27}', '127.0.0.1', '2026-11-07 18:20:37.947554');
INSERT INTO public.sys_operation_log VALUES (1392, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:22:08.761598');
INSERT INTO public.sys_operation_log VALUES (1415, 31, 30, 'biz_quote', 10, 'CREATE', NULL, '{"price": "812.0", "quantity": "20000"}', '127.0.0.1', '2026-11-07 18:22:38.782052');
INSERT INTO public.sys_operation_log VALUES (1452, 28, 27, 'biz_waybill', 6, 'STATUS PENDING_ACCEPT->PENDING_DEPART', '{"status": "PENDING_ACCEPT"}', '{"status": "PENDING_DEPART"}', '127.0.0.1', '2026-11-07 18:22:40.266099');
INSERT INTO public.sys_operation_log VALUES (1480, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:25:34.502486');
INSERT INTO public.sys_operation_log VALUES (1501, 27, 26, 'biz_demand', 10, 'STATUS WITHDRAWN->SUBMITTED', '{"status": "WITHDRAWN", "version": 1}', '{"status": "SUBMITTED", "version": 2}', '127.0.0.1', '2026-11-07 18:27:46.358209');
INSERT INTO public.sys_operation_log VALUES (1537, 37, 36, 'sys_file', 86, 'UPLOAD', NULL, '{"fileName": "stamp-supplier-1108022743.png", "size": 28}', '127.0.0.1', '2026-11-07 18:27:48.163247');
INSERT INTO public.sys_operation_log VALUES (1567, 37, 36, 'biz_settlement', 5, 'STATUS PENDING_CONFIRM_SUPPLIER->PENDING_CONFIRM_BUYER', '{"status": "PENDING_CONFIRM_SUPPLIER"}', '{"status": "PENDING_CONFIRM_BUYER"}', '127.0.0.1', '2026-11-07 18:27:49.558901');
INSERT INTO public.sys_operation_log VALUES (1097, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:33:27.089304');
INSERT INTO public.sys_operation_log VALUES (1119, 27, 26, 'biz_inquiry', 2, 'STATUS DRAFT->SENT', '{"status": "DRAFT"}', '{"status": "SENT"}', '127.0.0.1', '2026-11-07 17:34:37.544902');
INSERT INTO public.sys_operation_log VALUES (1120, 27, 26, 'biz_demand', 2, 'STATUS SUBMITTED->INQUIRING', '{"status": "SUBMITTED"}', '{"status": "INQUIRING"}', '127.0.0.1', '2026-11-07 17:34:37.544902');
INSERT INTO public.sys_operation_log VALUES (1147, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:40:15.485941');
INSERT INTO public.sys_operation_log VALUES (1172, 28, 27, 'biz_waybill', 1, 'STATUS IN_TRANSIT->ARRIVED', '{"status": "IN_TRANSIT"}', '{"status": "ARRIVED"}', '127.0.0.1', '2026-11-07 17:42:26.383346');
INSERT INTO public.sys_operation_log VALUES (1173, 28, 27, 'biz_waybill', 1, 'NODE ARRIVE', NULL, '{"node": "ARRIVE", "nodeTime": "2026-11-08 01:42:24", "remark": "到厂"}', '127.0.0.1', '2026-11-07 17:42:26.383346');
INSERT INTO public.sys_operation_log VALUES (1196, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:44:41.578077');
INSERT INTO public.sys_operation_log VALUES (1217, 1, NULL, 'ent_company', 30, 'STATUS PENDING->APPROVED', '{"status": "PENDING"}', '{"status": "APPROVED"}', '127.0.0.1', '2026-11-07 18:17:01.740999');
INSERT INTO public.sys_operation_log VALUES (1241, 31, 30, 'biz_bargain', 5, 'STATUS PENDING->ACCEPTED', '{"status": "PENDING"}', '{"status": "ACCEPTED"}', '127.0.0.1', '2026-11-07 18:17:03.511285');
INSERT INTO public.sys_operation_log VALUES (1280, 28, 27, 'biz_waybill', 3, 'STATUS PENDING_ACCEPT->PENDING_DEPART', '{"status": "PENDING_ACCEPT"}', '{"status": "PENDING_DEPART"}', '127.0.0.1', '2026-11-07 18:17:05.109745');
INSERT INTO public.sys_operation_log VALUES (1305, NULL, NULL, 'sys_user', 32, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:18:30.694774');
INSERT INTO public.sys_operation_log VALUES (1328, 31, 30, 'biz_quote', 7, 'CREATE', NULL, '{"price": "812.0", "quantity": "20000"}', '127.0.0.1', '2026-11-07 18:20:36.397943');
INSERT INTO public.sys_operation_log VALUES (1365, 28, 27, 'biz_waybill', 4, 'STATUS PENDING_ACCEPT->PENDING_DEPART', '{"status": "PENDING_ACCEPT"}', '{"status": "PENDING_DEPART"}', '127.0.0.1', '2026-11-07 18:20:37.978135');
INSERT INTO public.sys_operation_log VALUES (1393, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:22:36.420581');
INSERT INTO public.sys_operation_log VALUES (1416, 27, 26, 'biz_inquiry', 6, 'STATUS QUOTING->CLOSED', '{"status": "QUOTING"}', '{"status": "CLOSED"}', '127.0.0.1', '2026-11-07 18:22:38.943731');
INSERT INTO public.sys_operation_log VALUES (1453, 28, 27, 'biz_waybill', 6, 'STATUS PENDING_DEPART->IN_TRANSIT', '{"status": "PENDING_DEPART"}', '{"status": "IN_TRANSIT"}', '127.0.0.1', '2026-11-07 18:22:40.298801');
INSERT INTO public.sys_operation_log VALUES (1454, 28, 27, 'biz_waybill', 6, 'NODE DEPART', NULL, '{"node": "DEPART", "actualQty": 10000}', '127.0.0.1', '2026-11-07 18:22:40.298801');
INSERT INTO public.sys_operation_log VALUES (1481, 1, NULL, 'base_variety', 6, 'UPDATE', '{"id": 6, "variety_code": "PB", "variety_name": "PB粉", "default_grade": "999.00", "unit": "吨", "sort_no": 0, "status": "ENABLED", "created_at": "2026-11-07 16:07:48", "updated_at": "2026-11-07 18:17:02", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"default_grade": "61.5"}', '127.0.0.1', '2026-11-07 18:25:34.629789');
INSERT INTO public.sys_operation_log VALUES (1502, 27, 26, 'biz_inquiry', 7, 'CREATE', NULL, '{"quantity": "20000", "invites": [25, 35, 36]}', '127.0.0.1', '2026-11-07 18:27:46.437202');
INSERT INTO public.sys_operation_log VALUES (1538, 37, 36, 'biz_contract', 9, 'STATUS PENDING_SUPPLIER->EFFECTIVE', '{"status": "PENDING_SUPPLIER"}', '{"status": "EFFECTIVE"}', '127.0.0.1', '2026-11-07 18:27:48.192071');
INSERT INTO public.sys_operation_log VALUES (1539, 37, 36, 'biz_order', 5, 'STATUS PENDING_EFFECT->PERFORMING', '{"status": "PENDING_EFFECT"}', '{"status": "PERFORMING"}', '127.0.0.1', '2026-11-07 18:27:48.192071');
INSERT INTO public.sys_operation_log VALUES (1540, 37, 36, 'biz_contract', 9, 'SIGN(供方)', NULL, '{"signerName": "供方经办", "fileSha256": "927625f17b811ff5410a97b1712222fca33f113aaf40059f3192d2e76ff83879"}', '127.0.0.1', '2026-11-07 18:27:48.192071');
INSERT INTO public.sys_operation_log VALUES (1568, 27, 26, 'biz_settlement', 5, 'STATUS PENDING_CONFIRM_BUYER->CONFIRMED', '{"status": "PENDING_CONFIRM_BUYER"}', '{"status": "CONFIRMED"}', '127.0.0.1', '2026-11-07 18:27:49.639502');
INSERT INTO public.sys_operation_log VALUES (1098, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:33:29.220621');
INSERT INTO public.sys_operation_log VALUES (1121, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:37:19.992425');
INSERT INTO public.sys_operation_log VALUES (1148, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:40:17.614998');
INSERT INTO public.sys_operation_log VALUES (1174, 27, 26, 'biz_waybill', 1, 'STATUS ARRIVED->SIGNED', '{"status": "ARRIVED"}', '{"status": "SIGNED"}', '127.0.0.1', '2026-11-07 17:42:30.532681');
INSERT INTO public.sys_operation_log VALUES (1175, 27, 26, 'biz_waybill', 1, 'SIGN', NULL, '{"signerName": "李钢", "actualQty": 20000}', '127.0.0.1', '2026-11-07 17:42:30.532681');
INSERT INTO public.sys_operation_log VALUES (1197, NULL, NULL, 'sys_user', 28, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:44:43.91936');
INSERT INTO public.sys_operation_log VALUES (1218, NULL, NULL, 'sys_user', 29, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:17:01.768825');
INSERT INTO public.sys_operation_log VALUES (1242, 27, 26, 'biz_bargain', 6, 'CREATE', NULL, '{"quoteId": 4, "roundNo": 3, "initiator": "BUYER"}', '127.0.0.1', '2026-11-07 18:17:03.555875');
INSERT INTO public.sys_operation_log VALUES (1281, 28, 27, 'biz_waybill', 3, 'STATUS PENDING_DEPART->IN_TRANSIT', '{"status": "PENDING_DEPART"}', '{"status": "IN_TRANSIT"}', '127.0.0.1', '2026-11-07 18:17:05.153605');
INSERT INTO public.sys_operation_log VALUES (1282, 28, 27, 'biz_waybill', 3, 'NODE DEPART', NULL, '{"node": "DEPART"}', '127.0.0.1', '2026-11-07 18:17:05.153605');
INSERT INTO public.sys_operation_log VALUES (1306, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:20:34.005229');
INSERT INTO public.sys_operation_log VALUES (1329, 27, 26, 'biz_inquiry', 5, 'STATUS QUOTING->CLOSED', '{"status": "QUOTING"}', '{"status": "CLOSED"}', '127.0.0.1', '2026-11-07 18:20:36.598722');
INSERT INTO public.sys_operation_log VALUES (1366, 28, 27, 'biz_waybill', 4, 'STATUS PENDING_DEPART->IN_TRANSIT', '{"status": "PENDING_DEPART"}', '{"status": "IN_TRANSIT"}', '127.0.0.1', '2026-11-07 18:20:38.024175');
INSERT INTO public.sys_operation_log VALUES (1367, 28, 27, 'biz_waybill', 4, 'NODE DEPART', NULL, '{"node": "DEPART", "actualQty": 10000}', '127.0.0.1', '2026-11-07 18:20:38.024175');
INSERT INTO public.sys_operation_log VALUES (1394, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:22:36.852199');
INSERT INTO public.sys_operation_log VALUES (1417, 27, 26, 'biz_inquiry', 6, 'STATUS CLOSED->BARGAINING', '{"status": "CLOSED"}', '{"status": "BARGAINING"}', '127.0.0.1', '2026-11-07 18:22:38.981376');
INSERT INTO public.sys_operation_log VALUES (1418, 27, 26, 'biz_bargain', 10, 'CREATE', NULL, '{"quoteId": 10, "roundNo": 1, "initiator": "BUYER"}', '127.0.0.1', '2026-11-07 18:22:38.981376');
INSERT INTO public.sys_operation_log VALUES (1455, 28, 27, 'biz_waybill', 6, 'STATUS IN_TRANSIT->ARRIVED', '{"status": "IN_TRANSIT"}', '{"status": "ARRIVED"}', '127.0.0.1', '2026-11-07 18:22:40.33255');
INSERT INTO public.sys_operation_log VALUES (1456, 28, 27, 'biz_waybill', 6, 'NODE ARRIVE', NULL, '{"node": "ARRIVE"}', '127.0.0.1', '2026-11-07 18:22:40.33255');
INSERT INTO public.sys_operation_log VALUES (1482, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:27:43.816344');
INSERT INTO public.sys_operation_log VALUES (1503, 27, 26, 'biz_inquiry', 7, 'STATUS DRAFT->SENT', '{"status": "DRAFT"}', '{"status": "SENT"}', '127.0.0.1', '2026-11-07 18:27:46.497346');
INSERT INTO public.sys_operation_log VALUES (1504, 27, 26, 'biz_demand', 10, 'STATUS SUBMITTED->INQUIRING', '{"status": "SUBMITTED"}', '{"status": "INQUIRING"}', '127.0.0.1', '2026-11-07 18:27:46.497346');
INSERT INTO public.sys_operation_log VALUES (1541, 27, 26, 'biz_logistics_plan', 5, 'CREATE', NULL, '{"orgMode": "PLATFORM", "remark": "E2E 物流"}', '127.0.0.1', '2026-11-07 18:27:48.398959');
INSERT INTO public.sys_operation_log VALUES (1569, 27, 26, 'biz_settlement', 5, 'STATUS CONFIRMED->COMPLETED', '{"status": "CONFIRMED"}', '{"status": "COMPLETED"}', '127.0.0.1', '2026-11-07 18:27:49.674233');
INSERT INTO public.sys_operation_log VALUES (1570, 27, 26, 'biz_payment', 6, 'CREATE', NULL, '{"paymentNo": "FK-20261108-0006", "amount": "16523000.0"}', '127.0.0.1', '2026-11-07 18:27:49.674233');
INSERT INTO public.sys_operation_log VALUES (1099, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:33:31.352009');
INSERT INTO public.sys_operation_log VALUES (1122, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:37:22.121493');
INSERT INTO public.sys_operation_log VALUES (1149, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:40:19.749631');
INSERT INTO public.sys_operation_log VALUES (1176, 27, 26, 'biz_quality_check', 1, 'CREATE', NULL, '{"checkNo": "ZJ-20261108-0002", "arrivedQty": "18000", "conclusion": "ACCEPT"}', '127.0.0.1', '2026-11-07 17:42:34.892438');
INSERT INTO public.sys_operation_log VALUES (1198, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:47:03.876879');
INSERT INTO public.sys_operation_log VALUES (1219, NULL, NULL, 'sys_user', 30, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:17:01.895743');
INSERT INTO public.sys_operation_log VALUES (1243, 31, 30, 'biz_bargain', 6, 'STATUS PENDING->ACCEPTED', '{"status": "PENDING"}', '{"status": "ACCEPTED"}', '127.0.0.1', '2026-11-07 18:17:03.601483');
INSERT INTO public.sys_operation_log VALUES (1283, 28, 27, 'biz_waybill', 3, 'STATUS IN_TRANSIT->ARRIVED', '{"status": "IN_TRANSIT"}', '{"status": "ARRIVED"}', '127.0.0.1', '2026-11-07 18:17:05.185682');
INSERT INTO public.sys_operation_log VALUES (1284, 28, 27, 'biz_waybill', 3, 'NODE ARRIVE', NULL, '{"node": "ARRIVE"}', '127.0.0.1', '2026-11-07 18:17:05.185682');
INSERT INTO public.sys_operation_log VALUES (1307, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:20:34.422849');
INSERT INTO public.sys_operation_log VALUES (1330, 27, 26, 'biz_inquiry', 5, 'STATUS CLOSED->BARGAINING', '{"status": "CLOSED"}', '{"status": "BARGAINING"}', '127.0.0.1', '2026-11-07 18:20:36.636199');
INSERT INTO public.sys_operation_log VALUES (1331, 27, 26, 'biz_bargain', 7, 'CREATE', NULL, '{"quoteId": 7, "roundNo": 1, "initiator": "BUYER"}', '127.0.0.1', '2026-11-07 18:20:36.636199');
INSERT INTO public.sys_operation_log VALUES (1368, 28, 27, 'biz_waybill', 4, 'STATUS IN_TRANSIT->ARRIVED', '{"status": "IN_TRANSIT"}', '{"status": "ARRIVED"}', '127.0.0.1', '2026-11-07 18:20:38.05933');
INSERT INTO public.sys_operation_log VALUES (1369, 28, 27, 'biz_waybill', 4, 'NODE ARRIVE', NULL, '{"node": "ARRIVE"}', '127.0.0.1', '2026-11-07 18:20:38.05933');
INSERT INTO public.sys_operation_log VALUES (1395, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:22:36.943622');
INSERT INTO public.sys_operation_log VALUES (1419, 31, 30, 'biz_bargain', 10, 'STATUS PENDING->ACCEPTED', '{"status": "PENDING"}', '{"status": "ACCEPTED"}', '127.0.0.1', '2026-11-07 18:22:39.067515');
INSERT INTO public.sys_operation_log VALUES (1457, 27, 26, 'biz_waybill', 6, 'STATUS ARRIVED->SIGNED', '{"status": "ARRIVED"}', '{"status": "SIGNED"}', '127.0.0.1', '2026-11-07 18:22:40.389647');
INSERT INTO public.sys_operation_log VALUES (1458, 27, 26, 'biz_waybill', 6, 'SIGN', NULL, '{}', '127.0.0.1', '2026-11-07 18:22:40.389647');
INSERT INTO public.sys_operation_log VALUES (1483, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:27:44.249522');
INSERT INTO public.sys_operation_log VALUES (1505, 26, 25, 'biz_inquiry', 7, 'STATUS SENT->QUOTING', '{"status": "SENT"}', '{"status": "QUOTING"}', '127.0.0.1', '2026-11-07 18:27:46.612719');
INSERT INTO public.sys_operation_log VALUES (1506, 26, 25, 'biz_quote', 11, 'CREATE', NULL, '{"price": "818.0", "quantity": "20000"}', '127.0.0.1', '2026-11-07 18:27:46.612719');
INSERT INTO public.sys_operation_log VALUES (1542, 27, 26, 'biz_waybill', 8, 'DEVIATION', NULL, '{"deviationRate": "50.00%", "reason": "首段运力有限，剩余量由第二段补齐"}', '127.0.0.1', '2026-11-07 18:27:48.505393');
INSERT INTO public.sys_operation_log VALUES (1543, 27, 26, 'biz_waybill', 8, 'CREATE', NULL, '{"planQty": "10000", "status": "PENDING_ASSIGN"}', '127.0.0.1', '2026-11-07 18:27:48.505393');
INSERT INTO public.sys_operation_log VALUES (1571, 27, 26, 'biz_order', 5, 'STATUS PERFORMING->COMPLETED', '{"status": "PERFORMING"}', '{"status": "COMPLETED"}', '127.0.0.1', '2026-11-07 18:27:49.7588');
INSERT INTO public.sys_operation_log VALUES (1100, 1, NULL, 'base_price', 1, 'UPDATE', '{"id": 1, "variety_id": 6, "price_date": "2026-11-08", "price": "818.00", "price_basis": "WET", "source_desc": null, "remark": null, "created_at": "2026-11-07 17:32:22", "updated_at": "2026-11-07 17:33:08", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"price": "815.50", "priceBasis": null}', '127.0.0.1', '2026-11-07 17:33:33.481248');
INSERT INTO public.sys_operation_log VALUES (1123, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:37:24.258284');
INSERT INTO public.sys_operation_log VALUES (1150, 27, 26, 'sys_file', 62, 'UPLOAD', NULL, '{"fileName": "puyang_seal.png", "size": 70}', '127.0.0.1', '2026-11-07 17:40:26.950911');
INSERT INTO public.sys_operation_log VALUES (1177, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:42:52.196196');
INSERT INTO public.sys_operation_log VALUES (1199, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:47:09.68819');
INSERT INTO public.sys_operation_log VALUES (1220, NULL, NULL, 'sys_user', 31, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:17:01.97602');
INSERT INTO public.sys_operation_log VALUES (1244, 27, 26, 'biz_quote', 4, 'STATUS BARGAINING->WIN', '{"status": "BARGAINING"}', '{"status": "WIN"}', '127.0.0.1', '2026-11-07 18:17:03.679607');
INSERT INTO public.sys_operation_log VALUES (1245, 27, 26, 'biz_quote', 2, 'STATUS REVEALED->LOSE', '{"status": "REVEALED"}', '{"status": "LOSE"}', '127.0.0.1', '2026-11-07 18:17:03.679607');
INSERT INTO public.sys_operation_log VALUES (1246, 27, 26, 'biz_quote', 3, 'STATUS REVEALED->LOSE', '{"status": "REVEALED"}', '{"status": "LOSE"}', '127.0.0.1', '2026-11-07 18:17:03.679607');
INSERT INTO public.sys_operation_log VALUES (1247, 27, 26, 'biz_inquiry', 4, 'STATUS BARGAINING->AWARDED', '{"status": "BARGAINING"}', '{"status": "AWARDED"}', '127.0.0.1', '2026-11-07 18:17:03.679607');
INSERT INTO public.sys_operation_log VALUES (1248, 27, 26, 'biz_order', 2, 'AWARD', NULL, '{"quoteId": 4, "price": "806.00", "quantity": "20000.000"}', '127.0.0.1', '2026-11-07 18:17:03.679607');
INSERT INTO public.sys_operation_log VALUES (1285, 27, 26, 'biz_waybill', 3, 'STATUS ARRIVED->SIGNED', '{"status": "ARRIVED"}', '{"status": "SIGNED"}', '127.0.0.1', '2026-11-07 18:17:05.217016');
INSERT INTO public.sys_operation_log VALUES (1286, 27, 26, 'biz_waybill', 3, 'SIGN', NULL, '{}', '127.0.0.1', '2026-11-07 18:17:05.217016');
INSERT INTO public.sys_operation_log VALUES (1308, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:20:34.516429');
INSERT INTO public.sys_operation_log VALUES (1332, 31, 30, 'biz_bargain', 7, 'STATUS PENDING->ACCEPTED', '{"status": "PENDING"}', '{"status": "ACCEPTED"}', '127.0.0.1', '2026-11-07 18:20:36.706202');
INSERT INTO public.sys_operation_log VALUES (1370, 27, 26, 'biz_waybill', 4, 'STATUS ARRIVED->SIGNED', '{"status": "ARRIVED"}', '{"status": "SIGNED"}', '127.0.0.1', '2026-11-07 18:20:38.112331');
INSERT INTO public.sys_operation_log VALUES (1371, 27, 26, 'biz_waybill', 4, 'SIGN', NULL, '{}', '127.0.0.1', '2026-11-07 18:20:38.112331');
INSERT INTO public.sys_operation_log VALUES (1396, NULL, NULL, 'sys_user', 28, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:22:37.023517');
INSERT INTO public.sys_operation_log VALUES (1420, 27, 26, 'biz_bargain', 11, 'CREATE', NULL, '{"quoteId": 10, "roundNo": 2, "initiator": "BUYER"}', '127.0.0.1', '2026-11-07 18:22:39.099877');
INSERT INTO public.sys_operation_log VALUES (1459, 27, 26, 'biz_waybill', 7, 'CREATE', NULL, '{"planQty": "10000", "status": "PENDING_ACCEPT"}', '127.0.0.1', '2026-11-07 18:22:40.450099');
INSERT INTO public.sys_operation_log VALUES (1484, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:27:44.34142');
INSERT INTO public.sys_operation_log VALUES (1507, 36, 35, 'biz_quote', 12, 'CREATE', NULL, '{"price": "815.0", "quantity": "20000"}', '127.0.0.1', '2026-11-07 18:27:46.700394');
INSERT INTO public.sys_operation_log VALUES (1544, 27, 26, 'biz_waybill', 8, 'ASSIGN', NULL, '{"carrierId": 27}', '127.0.0.1', '2026-11-07 18:27:48.542853');
INSERT INTO public.sys_operation_log VALUES (1572, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:38:14.458445');
INSERT INTO public.sys_operation_log VALUES (1101, 1, NULL, 'base_price', 2, 'UPDATE', '{"id": 2, "variety_id": 7, "price_date": "2026-11-08", "price": "862.00", "price_basis": "WET", "source_desc": "中华混一号港口现货基准（E2E）", "remark": null, "created_at": "2026-11-07 17:32:24", "updated_at": "2026-11-07 17:33:06", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"price": "862.00", "priceBasis": null}', '127.0.0.1', '2026-11-07 17:33:35.550401');
INSERT INTO public.sys_operation_log VALUES (1124, 26, 25, 'biz_inquiry', 2, 'STATUS SENT->QUOTING', '{"status": "SENT"}', '{"status": "QUOTING"}', '127.0.0.1', '2026-11-07 17:37:26.373918');
INSERT INTO public.sys_operation_log VALUES (1125, 26, 25, 'biz_quote', 1, 'CREATE', NULL, '{"price": "830.0", "quantity": "20000"}', '127.0.0.1', '2026-11-07 17:37:26.373918');
INSERT INTO public.sys_operation_log VALUES (1151, 27, 26, 'biz_contract', 1, 'STATUS PENDING_BUYER->PENDING_SUPPLIER', '{"status": "PENDING_BUYER"}', '{"status": "PENDING_SUPPLIER"}', '127.0.0.1', '2026-11-07 17:40:29.035965');
INSERT INTO public.sys_operation_log VALUES (1152, 27, 26, 'biz_contract', 1, 'SIGN(需方)', NULL, '{"signerName": "李钢", "fileSha256": "497790947d4666760ce38f3c00e852c71fdb66cae849bae8e9ede352719e1581"}', '127.0.0.1', '2026-11-07 17:40:29.035965');
INSERT INTO public.sys_operation_log VALUES (1178, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:42:54.311798');
INSERT INTO public.sys_operation_log VALUES (1200, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:53:11.345211');
INSERT INTO public.sys_operation_log VALUES (1221, 1, NULL, 'base_variety', 6, 'UPDATE', '{"id": 6, "variety_code": "PB", "variety_name": "PB粉", "default_grade": "61.50", "unit": "吨", "sort_no": 0, "status": "ENABLED", "created_at": "2026-11-07 16:07:48", "updated_at": "2026-11-07 16:07:48", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"default_grade": "999"}', '127.0.0.1', '2026-11-07 18:17:02.11284');
INSERT INTO public.sys_operation_log VALUES (1249, 31, 30, 'biz_order', 2, 'STATUS PENDING_CONFIRM->PENDING_CONTRACT', '{"status": "PENDING_CONFIRM"}', '{"status": "PENDING_CONTRACT"}', '127.0.0.1', '2026-11-07 18:17:03.949374');
INSERT INTO public.sys_operation_log VALUES (1287, 27, 26, 'biz_quality_check', 2, 'CREATE', NULL, '{"checkNo": "ZJ-20261108-0003", "arrivedQty": "25000", "conclusion": "ACCEPT"}', '127.0.0.1', '2026-11-07 18:17:05.354805');
INSERT INTO public.sys_operation_log VALUES (1309, NULL, NULL, 'sys_user', 28, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:20:34.609263');
INSERT INTO public.sys_operation_log VALUES (1333, 27, 26, 'biz_bargain', 8, 'CREATE', NULL, '{"quoteId": 7, "roundNo": 2, "initiator": "BUYER"}', '127.0.0.1', '2026-11-07 18:20:36.738064');
INSERT INTO public.sys_operation_log VALUES (1372, 27, 26, 'biz_waybill', 5, 'CREATE', NULL, '{"planQty": "10000", "status": "PENDING_ACCEPT"}', '127.0.0.1', '2026-11-07 18:20:38.18638');
INSERT INTO public.sys_operation_log VALUES (1397, NULL, NULL, 'ent_company', 33, 'REGISTER', NULL, '{"companyName": "E2E钢厂二1108022236"}', '127.0.0.1', '2026-11-07 18:22:37.15074');
INSERT INTO public.sys_operation_log VALUES (1421, 31, 30, 'biz_bargain', 11, 'STATUS PENDING->ACCEPTED', '{"status": "PENDING"}', '{"status": "ACCEPTED"}', '127.0.0.1', '2026-11-07 18:22:39.145318');
INSERT INTO public.sys_operation_log VALUES (1460, 28, 27, 'biz_waybill', 7, 'STATUS PENDING_ACCEPT->PENDING_DEPART', '{"status": "PENDING_ACCEPT"}', '{"status": "PENDING_DEPART"}', '127.0.0.1', '2026-11-07 18:22:40.484438');
INSERT INTO public.sys_operation_log VALUES (1485, NULL, NULL, 'sys_user', 28, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:27:44.422036');
INSERT INTO public.sys_operation_log VALUES (1508, 37, 36, 'biz_quote', 13, 'CREATE', NULL, '{"price": "812.0", "quantity": "20000"}', '127.0.0.1', '2026-11-07 18:27:46.792727');
INSERT INTO public.sys_operation_log VALUES (1545, 28, 27, 'biz_waybill', 8, 'STATUS PENDING_ACCEPT->PENDING_DEPART', '{"status": "PENDING_ACCEPT"}', '{"status": "PENDING_DEPART"}', '127.0.0.1', '2026-11-07 18:27:48.575219');
INSERT INTO public.sys_operation_log VALUES (1573, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:39:07.792505');
INSERT INTO public.sys_operation_log VALUES (1102, 1, NULL, 'base_price', 1, 'UPDATE', '{"id": 1, "variety_id": 6, "price_date": "2026-11-08", "price": "815.50", "price_basis": "WET", "source_desc": "进口PB粉港口现货基准（E2E）", "remark": null, "created_at": "2026-11-07 17:32:22", "updated_at": "2026-11-07 17:33:33", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"price": "818.00", "priceBasis": null}', '127.0.0.1', '2026-11-07 17:33:37.617028');
INSERT INTO public.sys_operation_log VALUES (1126, 26, 25, 'biz_quote', 1, 'UPDATE', '{"id": 1, "quote_no": "BJ-20261108-0001", "inquiry_id": 2, "supplier_id": 25, "price": "830.00", "quantity": "20000.000", "delivery_date": "2026-11-18", "delivery_place": "曹妃甸港", "pay_terms": "信用证30天", "quality_commit": "以港检为准", "valid_until": "2026-11-15", "remark": "首报", "version": 1, "status": "SUBMITTED", "created_at": "2026-11-07 17:37:26", "updated_at": "2026-11-07 17:37:26", "created_by": 26, "updated_by": 26, "is_deleted": 0}', '{"price": "832.0", "quantity": "20000", "version": 2}', '127.0.0.1', '2026-11-07 17:37:28.44367');
INSERT INTO public.sys_operation_log VALUES (1153, 26, 25, 'sys_file', 63, 'UPLOAD', NULL, '{"fileName": "cmgroup_seal.png", "size": 70}', '127.0.0.1', '2026-11-07 17:40:31.285204');
INSERT INTO public.sys_operation_log VALUES (1179, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:42:56.444537');
INSERT INTO public.sys_operation_log VALUES (1201, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:53:58.936567');
INSERT INTO public.sys_operation_log VALUES (1222, 1, NULL, 'base_price', 3, 'CREATE', NULL, '{"varietyId": 6, "priceDate": "2026-11-08", "price": 820.5, "priceBasis": "WET", "sourceDesc": "E2E 录入"}', '127.0.0.1', '2026-11-07 18:17:02.177276');
INSERT INTO public.sys_operation_log VALUES (1250, 27, 26, 'biz_contract', 2, 'STATUS PENDING_GENERATE->PENDING_BUYER', '{"status": "PENDING_GENERATE"}', '{"status": "PENDING_BUYER"}', '127.0.0.1', '2026-11-07 18:17:04.050327');
INSERT INTO public.sys_operation_log VALUES (1251, 27, 26, 'biz_order', 2, 'STATUS PENDING_CONTRACT->PENDING_EFFECT', '{"status": "PENDING_CONTRACT"}', '{"status": "PENDING_EFFECT"}', '127.0.0.1', '2026-11-07 18:17:04.050327');
INSERT INTO public.sys_operation_log VALUES (1252, 27, 26, 'biz_contract', 2, 'GENERATE', NULL, '{"version": 1}', '127.0.0.1', '2026-11-07 18:17:04.050327');
INSERT INTO public.sys_operation_log VALUES (1288, 27, 26, 'biz_alert', 2, 'STATUS PENDING->PROCESSING', '{"status": "PENDING"}', '{"status": "PROCESSING"}', '127.0.0.1', '2026-11-07 18:17:05.448848');
INSERT INTO public.sys_operation_log VALUES (1310, NULL, NULL, 'ent_company', 32, 'REGISTER', NULL, '{"companyName": "E2E钢厂二1108022034"}', '127.0.0.1', '2026-11-07 18:20:34.735576');
INSERT INTO public.sys_operation_log VALUES (1334, 31, 30, 'biz_bargain', 8, 'STATUS PENDING->ACCEPTED', '{"status": "PENDING"}', '{"status": "ACCEPTED"}', '127.0.0.1', '2026-11-07 18:20:36.764573');
INSERT INTO public.sys_operation_log VALUES (1373, 28, 27, 'biz_waybill', 5, 'STATUS PENDING_ACCEPT->PENDING_DEPART', '{"status": "PENDING_ACCEPT"}', '{"status": "PENDING_DEPART"}', '127.0.0.1', '2026-11-07 18:20:38.239635');
INSERT INTO public.sys_operation_log VALUES (1398, 1, NULL, 'ent_company', 33, 'STATUS PENDING->APPROVED', '{"status": "PENDING"}', '{"status": "APPROVED"}', '127.0.0.1', '2026-11-07 18:22:37.403068');
INSERT INTO public.sys_operation_log VALUES (1422, 27, 26, 'biz_bargain', 12, 'CREATE', NULL, '{"quoteId": 10, "roundNo": 3, "initiator": "BUYER"}', '127.0.0.1', '2026-11-07 18:22:39.191231');
INSERT INTO public.sys_operation_log VALUES (1461, 28, 27, 'biz_waybill', 7, 'STATUS PENDING_DEPART->IN_TRANSIT', '{"status": "PENDING_DEPART"}', '{"status": "IN_TRANSIT"}', '127.0.0.1', '2026-11-07 18:22:40.515811');
INSERT INTO public.sys_operation_log VALUES (1462, 28, 27, 'biz_waybill', 7, 'NODE DEPART', NULL, '{"node": "DEPART"}', '127.0.0.1', '2026-11-07 18:22:40.515811');
INSERT INTO public.sys_operation_log VALUES (1486, NULL, NULL, 'ent_company', 34, 'REGISTER', NULL, '{"companyName": "E2E钢厂二1108022743"}', '127.0.0.1', '2026-11-07 18:27:44.544524');
INSERT INTO public.sys_operation_log VALUES (1509, 27, 26, 'biz_inquiry', 7, 'STATUS QUOTING->CLOSED', '{"status": "QUOTING"}', '{"status": "CLOSED"}', '127.0.0.1', '2026-11-07 18:27:47.010278');
INSERT INTO public.sys_operation_log VALUES (1546, 28, 27, 'biz_waybill', 8, 'STATUS PENDING_DEPART->IN_TRANSIT', '{"status": "PENDING_DEPART"}', '{"status": "IN_TRANSIT"}', '127.0.0.1', '2026-11-07 18:27:48.615052');
INSERT INTO public.sys_operation_log VALUES (1547, 28, 27, 'biz_waybill', 8, 'NODE DEPART', NULL, '{"node": "DEPART", "actualQty": 10000}', '127.0.0.1', '2026-11-07 18:27:48.615052');
INSERT INTO public.sys_operation_log VALUES (1574, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-08 02:53:00.861672');
INSERT INTO public.sys_operation_log VALUES (1127, 27, 26, 'biz_inquiry', 2, 'STATUS QUOTING->CLOSED', '{"status": "QUOTING"}', '{"status": "CLOSED"}', '127.0.0.1', '2026-11-07 17:37:36.935265');
INSERT INTO public.sys_operation_log VALUES (1154, 26, 25, 'biz_contract', 1, 'STATUS PENDING_SUPPLIER->EFFECTIVE', '{"status": "PENDING_SUPPLIER"}', '{"status": "EFFECTIVE"}', '127.0.0.1', '2026-11-07 17:40:33.364388');
INSERT INTO public.sys_operation_log VALUES (1155, 26, 25, 'biz_order', 1, 'STATUS PENDING_EFFECT->PERFORMING', '{"status": "PENDING_EFFECT"}', '{"status": "PERFORMING"}', '127.0.0.1', '2026-11-07 17:40:33.364388');
INSERT INTO public.sys_operation_log VALUES (1156, 26, 25, 'biz_contract', 1, 'SIGN(供方)', NULL, '{"signerName": "王矿", "fileSha256": "497790947d4666760ce38f3c00e852c71fdb66cae849bae8e9ede352719e1581"}', '127.0.0.1', '2026-11-07 17:40:33.364388');
INSERT INTO public.sys_operation_log VALUES (1180, NULL, NULL, 'sys_user', 28, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:42:58.747836');
INSERT INTO public.sys_operation_log VALUES (1202, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:10:17.083698');
INSERT INTO public.sys_operation_log VALUES (1223, 1, NULL, 'base_price', 3, 'UPDATE', '{"id": 3, "variety_id": 6, "price_date": "2026-11-08", "price": "820.50", "price_basis": "WET", "source_desc": "E2E 录入", "remark": null, "created_at": "2026-11-07 18:17:02", "updated_at": "2026-11-07 18:17:02", "created_by": 1, "updated_by": 1, "is_deleted": 0}', '{"price": 830.5, "priceBasis": "WET"}', '127.0.0.1', '2026-11-07 18:17:02.222179');
INSERT INTO public.sys_operation_log VALUES (1253, 27, 26, 'sys_file', 69, 'UPLOAD', NULL, '{"fileName": "stamp-buyer-1108021659.pdf", "size": 28}', '127.0.0.1', '2026-11-07 18:17:04.188336');
INSERT INTO public.sys_operation_log VALUES (1289, 27, 26, 'biz_alert', 2, 'STATUS PROCESSING->CLOSED', '{"status": "PROCESSING"}', '{"status": "CLOSED"}', '127.0.0.1', '2026-11-07 18:17:05.519802');
INSERT INTO public.sys_operation_log VALUES (1311, 1, NULL, 'ent_company', 32, 'STATUS PENDING->APPROVED', '{"status": "PENDING"}', '{"status": "APPROVED"}', '127.0.0.1', '2026-11-07 18:20:35.034959');
INSERT INTO public.sys_operation_log VALUES (1335, 27, 26, 'biz_bargain', 9, 'CREATE', NULL, '{"quoteId": 7, "roundNo": 3, "initiator": "BUYER"}', '127.0.0.1', '2026-11-07 18:20:36.815108');
INSERT INTO public.sys_operation_log VALUES (1374, 28, 27, 'biz_waybill', 5, 'STATUS PENDING_DEPART->IN_TRANSIT', '{"status": "PENDING_DEPART"}', '{"status": "IN_TRANSIT"}', '127.0.0.1', '2026-11-07 18:20:38.286184');
INSERT INTO public.sys_operation_log VALUES (1375, 28, 27, 'biz_waybill', 5, 'NODE DEPART', NULL, '{"node": "DEPART"}', '127.0.0.1', '2026-11-07 18:20:38.286184');
INSERT INTO public.sys_operation_log VALUES (1399, NULL, NULL, 'sys_user', 34, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:22:37.431709');
INSERT INTO public.sys_operation_log VALUES (1423, 31, 30, 'biz_bargain', 12, 'STATUS PENDING->ACCEPTED', '{"status": "PENDING"}', '{"status": "ACCEPTED"}', '127.0.0.1', '2026-11-07 18:22:39.221871');
INSERT INTO public.sys_operation_log VALUES (1463, 28, 27, 'biz_waybill', 7, 'STATUS IN_TRANSIT->ARRIVED', '{"status": "IN_TRANSIT"}', '{"status": "ARRIVED"}', '127.0.0.1', '2026-11-07 18:22:40.573043');
INSERT INTO public.sys_operation_log VALUES (1464, 28, 27, 'biz_waybill', 7, 'NODE ARRIVE', NULL, '{"node": "ARRIVE"}', '127.0.0.1', '2026-11-07 18:22:40.573043');
INSERT INTO public.sys_operation_log VALUES (1487, NULL, NULL, 'ent_company', 35, 'REGISTER', NULL, '{"companyName": "E2E补位供应商11108022743"}', '127.0.0.1', '2026-11-07 18:27:44.78567');
INSERT INTO public.sys_operation_log VALUES (1510, 27, 26, 'biz_inquiry', 7, 'STATUS CLOSED->BARGAINING', '{"status": "CLOSED"}', '{"status": "BARGAINING"}', '127.0.0.1', '2026-11-07 18:27:47.045757');
INSERT INTO public.sys_operation_log VALUES (1511, 27, 26, 'biz_bargain', 13, 'CREATE', NULL, '{"quoteId": 13, "roundNo": 1, "initiator": "BUYER"}', '127.0.0.1', '2026-11-07 18:27:47.045757');
INSERT INTO public.sys_operation_log VALUES (1548, 28, 27, 'biz_waybill', 8, 'STATUS IN_TRANSIT->ARRIVED', '{"status": "IN_TRANSIT"}', '{"status": "ARRIVED"}', '127.0.0.1', '2026-11-07 18:27:48.646743');
INSERT INTO public.sys_operation_log VALUES (1549, 28, 27, 'biz_waybill', 8, 'NODE ARRIVE', NULL, '{"node": "ARRIVE"}', '127.0.0.1', '2026-11-07 18:27:48.646743');
INSERT INTO public.sys_operation_log VALUES (1128, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:37:54.258895');
INSERT INTO public.sys_operation_log VALUES (1157, 27, 26, 'biz_logistics_plan', 1, 'CREATE', NULL, '{"orgMode": "PLATFORM", "remark": "港拖+汽运"}', '127.0.0.1', '2026-11-07 17:40:39.743542');
INSERT INTO public.sys_operation_log VALUES (1181, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:43:36.534875');
INSERT INTO public.sys_operation_log VALUES (1203, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:11:59.645634');
INSERT INTO public.sys_operation_log VALUES (1224, 27, 26, 'biz_demand', 4, 'CREATE', NULL, '{"demandName": "E2E 全链路需求1108021659"}', '127.0.0.1', '2026-11-07 18:17:02.423553');
INSERT INTO public.sys_operation_log VALUES (1254, 27, 26, 'biz_contract', 2, 'STATUS PENDING_BUYER->PENDING_SUPPLIER', '{"status": "PENDING_BUYER"}', '{"status": "PENDING_SUPPLIER"}', '127.0.0.1', '2026-11-07 18:17:04.216154');
INSERT INTO public.sys_operation_log VALUES (1255, 27, 26, 'biz_contract', 2, 'SIGN(需方)', NULL, '{"signerName": "需方经办", "fileSha256": "4b8f3ce960bc6d4fda6aee1099f7d37530ae5a8e719e163c1f1ed1036e5f8a11"}', '127.0.0.1', '2026-11-07 18:17:04.216154');
INSERT INTO public.sys_operation_log VALUES (1290, 27, 26, 'biz_quality_check', 3, 'CREATE', NULL, '{"checkNo": "ZJ-20261108-0004", "arrivedQty": "26000", "conclusion": "ACCEPT"}', '127.0.0.1', '2026-11-07 18:17:05.55079');
INSERT INTO public.sys_operation_log VALUES (1312, NULL, NULL, 'sys_user', 33, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:20:35.075785');
INSERT INTO public.sys_operation_log VALUES (1336, 31, 30, 'biz_bargain', 9, 'STATUS PENDING->ACCEPTED', '{"status": "PENDING"}', '{"status": "ACCEPTED"}', '127.0.0.1', '2026-11-07 18:20:36.862689');
INSERT INTO public.sys_operation_log VALUES (1376, 28, 27, 'biz_waybill', 5, 'STATUS IN_TRANSIT->ARRIVED', '{"status": "IN_TRANSIT"}', '{"status": "ARRIVED"}', '127.0.0.1', '2026-11-07 18:20:38.317668');
INSERT INTO public.sys_operation_log VALUES (1377, 28, 27, 'biz_waybill', 5, 'NODE ARRIVE', NULL, '{"node": "ARRIVE"}', '127.0.0.1', '2026-11-07 18:20:38.317668');
INSERT INTO public.sys_operation_log VALUES (1400, NULL, NULL, 'sys_user', 30, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:22:37.64038');
INSERT INTO public.sys_operation_log VALUES (1424, 27, 26, 'biz_quote', 10, 'STATUS BARGAINING->WIN', '{"status": "BARGAINING"}', '{"status": "WIN"}', '127.0.0.1', '2026-11-07 18:22:39.276488');
INSERT INTO public.sys_operation_log VALUES (1425, 27, 26, 'biz_quote', 8, 'STATUS REVEALED->LOSE', '{"status": "REVEALED"}', '{"status": "LOSE"}', '127.0.0.1', '2026-11-07 18:22:39.276488');
INSERT INTO public.sys_operation_log VALUES (1426, 27, 26, 'biz_quote', 9, 'STATUS REVEALED->LOSE', '{"status": "REVEALED"}', '{"status": "LOSE"}', '127.0.0.1', '2026-11-07 18:22:39.276488');
INSERT INTO public.sys_operation_log VALUES (1427, 27, 26, 'biz_inquiry', 6, 'STATUS BARGAINING->AWARDED', '{"status": "BARGAINING"}', '{"status": "AWARDED"}', '127.0.0.1', '2026-11-07 18:22:39.276488');
INSERT INTO public.sys_operation_log VALUES (1428, 27, 26, 'biz_order', 4, 'AWARD', NULL, '{"quoteId": 10, "price": "806.00", "quantity": "20000.000"}', '127.0.0.1', '2026-11-07 18:22:39.276488');
INSERT INTO public.sys_operation_log VALUES (1465, 27, 26, 'biz_waybill', 7, 'STATUS ARRIVED->SIGNED', '{"status": "ARRIVED"}', '{"status": "SIGNED"}', '127.0.0.1', '2026-11-07 18:22:40.605228');
INSERT INTO public.sys_operation_log VALUES (1466, 27, 26, 'biz_waybill', 7, 'SIGN', NULL, '{}', '127.0.0.1', '2026-11-07 18:22:40.605228');
INSERT INTO public.sys_operation_log VALUES (1488, NULL, NULL, 'ent_company', 36, 'REGISTER', NULL, '{"companyName": "E2E补位供应商21108022743"}', '127.0.0.1', '2026-11-07 18:27:44.947588');
INSERT INTO public.sys_operation_log VALUES (1512, 37, 36, 'biz_bargain', 13, 'STATUS PENDING->ACCEPTED', '{"status": "PENDING"}', '{"status": "ACCEPTED"}', '127.0.0.1', '2026-11-07 18:27:47.151031');
INSERT INTO public.sys_operation_log VALUES (1550, 27, 26, 'biz_waybill', 8, 'STATUS ARRIVED->SIGNED', '{"status": "ARRIVED"}', '{"status": "SIGNED"}', '127.0.0.1', '2026-11-07 18:27:48.72348');
INSERT INTO public.sys_operation_log VALUES (1551, 27, 26, 'biz_waybill', 8, 'SIGN', NULL, '{}', '127.0.0.1', '2026-11-07 18:27:48.72348');
INSERT INTO public.sys_operation_log VALUES (1129, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:37:56.393035');
INSERT INTO public.sys_operation_log VALUES (1158, 27, 26, 'biz_waybill', 1, 'CREATE', NULL, '{"planQty": "20000", "status": "PENDING_ASSIGN"}', '127.0.0.1', '2026-11-07 17:40:44.0423');
INSERT INTO public.sys_operation_log VALUES (1182, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:43:38.664259');
INSERT INTO public.sys_operation_log VALUES (1204, NULL, NULL, 'sys_user', 1, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:12:27.038113');
INSERT INTO public.sys_operation_log VALUES (1225, 27, 26, 'biz_demand', 4, 'UPDATE', NULL, '{"demandName": "E2E 全链路需求1108021659"}', '127.0.0.1', '2026-11-07 18:17:02.471502');
INSERT INTO public.sys_operation_log VALUES (1256, 27, 26, 'biz_contract', 2, 'STATUS PENDING_SUPPLIER->VOID', '{"status": "PENDING_SUPPLIER"}', '{"status": "VOID"}', '127.0.0.1', '2026-11-07 18:17:04.261843');
INSERT INTO public.sys_operation_log VALUES (1257, 27, 26, 'biz_order', 2, 'STATUS PENDING_EFFECT->PENDING_CONTRACT', '{"status": "PENDING_EFFECT"}', '{"status": "PENDING_CONTRACT"}', '127.0.0.1', '2026-11-07 18:17:04.261843');
INSERT INTO public.sys_operation_log VALUES (1258, 27, 26, 'biz_contract', 2, 'VOID', NULL, '{"reason": "E2E：条款调整，作废重签"}', '127.0.0.1', '2026-11-07 18:17:04.261843');
INSERT INTO public.sys_operation_log VALUES (1291, 27, 26, 'biz_alert', 3, 'STATUS PENDING->CLOSED', '{"status": "PENDING"}', '{"status": "CLOSED"}', '127.0.0.1', '2026-11-07 18:17:05.637081');
INSERT INTO public.sys_operation_log VALUES (1313, NULL, NULL, 'sys_user', 30, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:20:35.264154');
INSERT INTO public.sys_operation_log VALUES (1337, 27, 26, 'biz_quote', 7, 'STATUS BARGAINING->WIN', '{"status": "BARGAINING"}', '{"status": "WIN"}', '127.0.0.1', '2026-11-07 18:20:36.918898');
INSERT INTO public.sys_operation_log VALUES (1338, 27, 26, 'biz_quote', 5, 'STATUS REVEALED->LOSE', '{"status": "REVEALED"}', '{"status": "LOSE"}', '127.0.0.1', '2026-11-07 18:20:36.918898');
INSERT INTO public.sys_operation_log VALUES (1339, 27, 26, 'biz_quote', 6, 'STATUS REVEALED->LOSE', '{"status": "REVEALED"}', '{"status": "LOSE"}', '127.0.0.1', '2026-11-07 18:20:36.918898');
INSERT INTO public.sys_operation_log VALUES (1340, 27, 26, 'biz_inquiry', 5, 'STATUS BARGAINING->AWARDED', '{"status": "BARGAINING"}', '{"status": "AWARDED"}', '127.0.0.1', '2026-11-07 18:20:36.918898');
INSERT INTO public.sys_operation_log VALUES (1341, 27, 26, 'biz_order', 3, 'AWARD', NULL, '{"quoteId": 7, "price": "806.00", "quantity": "20000.000"}', '127.0.0.1', '2026-11-07 18:20:36.918898');
INSERT INTO public.sys_operation_log VALUES (1378, 27, 26, 'biz_waybill', 5, 'STATUS ARRIVED->SIGNED', '{"status": "ARRIVED"}', '{"status": "SIGNED"}', '127.0.0.1', '2026-11-07 18:20:38.34975');
INSERT INTO public.sys_operation_log VALUES (1379, 27, 26, 'biz_waybill', 5, 'SIGN', NULL, '{}', '127.0.0.1', '2026-11-07 18:20:38.34975');
INSERT INTO public.sys_operation_log VALUES (1401, NULL, NULL, 'sys_user', 31, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 18:22:37.798057');
INSERT INTO public.sys_operation_log VALUES (1429, 31, 30, 'biz_order', 4, 'STATUS PENDING_CONFIRM->PENDING_CONTRACT', '{"status": "PENDING_CONFIRM"}', '{"status": "PENDING_CONTRACT"}', '127.0.0.1', '2026-11-07 18:22:39.466934');
INSERT INTO public.sys_operation_log VALUES (1467, 27, 26, 'biz_quality_check', 8, 'CREATE', NULL, '{"checkNo": "ZJ-20261108-0009", "arrivedQty": "25000", "conclusion": "ACCEPT"}', '127.0.0.1', '2026-11-07 18:22:40.691781');
INSERT INTO public.sys_operation_log VALUES (1489, 1, NULL, 'ent_company', 34, 'STATUS PENDING->APPROVED', '{"status": "PENDING"}', '{"status": "APPROVED"}', '127.0.0.1', '2026-11-07 18:27:45.22858');
INSERT INTO public.sys_operation_log VALUES (1513, 27, 26, 'biz_bargain', 14, 'CREATE', NULL, '{"quoteId": 13, "roundNo": 2, "initiator": "BUYER"}', '127.0.0.1', '2026-11-07 18:27:47.197937');
INSERT INTO public.sys_operation_log VALUES (1552, 27, 26, 'biz_waybill', 9, 'CREATE', NULL, '{"planQty": "10000", "status": "PENDING_ACCEPT"}', '127.0.0.1', '2026-11-07 18:27:48.797727');
INSERT INTO public.sys_operation_log VALUES (1056, 1, NULL, 'base_variety', 6, 'CREATE', NULL, '{"varietyCode": "PB", "varietyName": "PB粉", "defaultGrade": "61.5", "unit": "吨"}', '127.0.0.1', '2026-11-07 16:07:48.880683');
INSERT INTO public.sys_operation_log VALUES (1057, 1, NULL, 'base_variety', 7, 'CREATE', NULL, '{"varietyCode": "ZHHYH", "varietyName": "中华混一号", "defaultGrade": "62.0", "unit": "吨"}', '127.0.0.1', '2026-11-07 16:08:05.097191');
INSERT INTO public.sys_operation_log VALUES (1066, NULL, NULL, 'ent_company', 25, 'REGISTER', NULL, '{"companyName": "中国矿产资源集团国际铁矿石贸易有限公司"}', '127.0.0.1', '2026-11-07 17:01:29.205031');
INSERT INTO public.sys_operation_log VALUES (1067, NULL, NULL, 'ent_company', 26, 'REGISTER', NULL, '{"companyName": "河北普阳钢铁有限公司"}', '127.0.0.1', '2026-11-07 17:03:27.780379');
INSERT INTO public.sys_operation_log VALUES (1070, 1, NULL, 'ent_company', 26, 'STATUS PENDING->APPROVED', '{"status": "PENDING"}', '{"status": "APPROVED"}', '127.0.0.1', '2026-11-07 17:07:29.943761');
INSERT INTO public.sys_operation_log VALUES (1071, 1, NULL, 'ent_company', 25, 'STATUS PENDING->APPROVED', '{"status": "PENDING"}', '{"status": "APPROVED"}', '127.0.0.1', '2026-11-07 17:07:48.130727');
INSERT INTO public.sys_operation_log VALUES (1072, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:08:28.20498');
INSERT INTO public.sys_operation_log VALUES (1073, NULL, NULL, 'sys_user', 27, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:08:49.910995');
INSERT INTO public.sys_operation_log VALUES (1075, 1, NULL, 'ent_company', 25, 'SET STATUS', NULL, '{"status": "DISABLED"}', '127.0.0.1', '2026-11-07 17:12:48.290663');
INSERT INTO public.sys_operation_log VALUES (1077, 1, NULL, 'ent_company', 25, 'SET STATUS', NULL, '{"status": "ENABLED"}', '127.0.0.1', '2026-11-07 17:14:26.992241');
INSERT INTO public.sys_operation_log VALUES (1078, NULL, NULL, 'sys_user', 26, 'LOGIN', NULL, NULL, '127.0.0.1', '2026-11-07 17:14:49.736227');


--
-- Data for Name: sys_seq; Type: TABLE DATA; Schema: public; Owner: postgres
--

INSERT INTO public.sys_seq VALUES ('2026-11-07', 'XQ', 10);
INSERT INTO public.sys_seq VALUES ('2026-11-07', 'XJ', 7);
INSERT INTO public.sys_seq VALUES ('2026-11-07', 'BJ', 13);
INSERT INTO public.sys_seq VALUES ('2026-11-07', 'DD', 5);
INSERT INTO public.sys_seq VALUES ('2026-11-07', 'HT', 9);
INSERT INTO public.sys_seq VALUES ('2026-11-07', 'WL', 5);
INSERT INTO public.sys_seq VALUES ('2026-11-07', 'YD', 9);
INSERT INTO public.sys_seq VALUES ('2026-11-07', 'YJ', 9);
INSERT INTO public.sys_seq VALUES ('2026-11-07', 'ZJ', 14);
INSERT INTO public.sys_seq VALUES ('2026-11-07', 'JS', 5);
INSERT INTO public.sys_seq VALUES ('2026-11-07', 'FK', 6);


--
-- Data for Name: sys_user; Type: TABLE DATA; Schema: public; Owner: postgres
--

INSERT INTO public.sys_user VALUES (1, NULL, '13800000000', '$2b$10$XXD3X5ClZQB8QBDS5PdmguV.mnUMchiE7uq8nnJg2cc3tJMAem25m', '平台管理员', 'PLAT_ADMIN', 'ENABLED', '2026-11-07 07:25:00.577978', '2026-11-07 07:25:00.577978', NULL, NULL, 0);
INSERT INTO public.sys_user VALUES (26, 25, '13900000001', '$2b$10$HriYJbYCCYsuALs9BNmI0uUL9ZvyubmoJiSPBNUVnUeS7BOfRK3MK', '王矿', 'SUPPLIER', 'ENABLED', '2026-11-07 17:01:29.205031', '2026-11-07 17:01:29.205031', 26, NULL, 0);
INSERT INTO public.sys_user VALUES (27, 26, '13900000002', '$2b$10$HriYJbYCCYsuALs9BNmI0uUL9ZvyubmoJiSPBNUVnUeS7BOfRK3MK', '李钢', 'STEEL_BUYER', 'ENABLED', '2026-11-07 17:03:27.780379', '2026-11-07 17:03:27.780379', 27, NULL, 0);
INSERT INTO public.sys_user VALUES (28, 27, '13900000003', '$2b$10$HriYJbYCCYsuALs9BNmI0uUL9ZvyubmoJiSPBNUVnUeS7BOfRK3MK', '张承运', 'LOGISTICS_CARRIER', 'ENABLED', '2026-11-07 17:42:00.206573', '2026-11-07 17:42:00.206573', 28, NULL, 0);


--
-- Name: base_price_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.base_price_id_seq', 6, true);


--
-- Name: base_variety_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.base_variety_id_seq', 7, true);


--
-- Name: biz_alert_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_alert_id_seq', 9, true);


--
-- Name: biz_bargain_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_bargain_id_seq', 15, true);


--
-- Name: biz_contract_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_contract_id_seq', 9, true);


--
-- Name: biz_demand_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_demand_id_seq', 10, true);


--
-- Name: biz_demand_item_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_demand_item_id_seq', 16, true);


--
-- Name: biz_forecast_quote_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_forecast_quote_id_seq', 1, false);


--
-- Name: biz_inquiry_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_inquiry_id_seq', 7, true);


--
-- Name: biz_inquiry_invite_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_inquiry_invite_id_seq', 15, true);


--
-- Name: biz_logistics_plan_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_logistics_plan_id_seq', 5, true);


--
-- Name: biz_order_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_order_id_seq', 5, true);


--
-- Name: biz_payment_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_payment_id_seq', 6, true);


--
-- Name: biz_quality_check_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_quality_check_id_seq', 13, true);


--
-- Name: biz_quote_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_quote_id_seq', 13, true);


--
-- Name: biz_settlement_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_settlement_id_seq', 5, true);


--
-- Name: biz_track_node_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_track_node_id_seq', 122, true);


--
-- Name: biz_waybill_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.biz_waybill_id_seq', 9, true);


--
-- Name: ent_company_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.ent_company_id_seq', 36, true);


--
-- Name: ent_qualification_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.ent_qualification_id_seq', 31, true);


--
-- Name: sys_file_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.sys_file_id_seq', 86, true);


--
-- Name: sys_message_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.sys_message_id_seq', 411, true);


--
-- Name: sys_operation_log_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.sys_operation_log_id_seq', 1574, true);


--
-- Name: sys_user_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.sys_user_id_seq', 37, true);


--
-- PostgreSQL database dump complete
--

\unrestrict tK7pRfonraDYDMGz4UD34fMVbVxrxTJVh90XmthIud5sBWvFwb7uSrbiy8z4eAe

