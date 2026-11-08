--
-- PostgreSQL database dump
--

\restrict Lb9KCfoXWj2kJULcRfyQrfbiHIqI2jFgsnsx78LK3zdukJ1VU1nKZE0iFrJpifh

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

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: base_price; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.base_price (
    id bigint NOT NULL,
    variety_id bigint NOT NULL,
    price_date date NOT NULL,
    price numeric(18,2) NOT NULL,
    price_basis character varying(16) DEFAULT 'WET'::character varying,
    source_desc character varying(200),
    remark character varying(200),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    updated_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.base_price OWNER TO postgres;

--
-- Name: base_price_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.base_price_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.base_price_id_seq OWNER TO postgres;

--
-- Name: base_price_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.base_price_id_seq OWNED BY public.base_price.id;


--
-- Name: base_variety; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.base_variety (
    id bigint NOT NULL,
    variety_code character varying(32) NOT NULL,
    variety_name character varying(64) NOT NULL,
    default_grade numeric(5,2),
    unit character varying(16) DEFAULT '吨'::character varying,
    sort_no integer DEFAULT 0,
    status character varying(20) DEFAULT 'ENABLED'::character varying,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    updated_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.base_variety OWNER TO postgres;

--
-- Name: base_variety_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.base_variety_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.base_variety_id_seq OWNER TO postgres;

--
-- Name: base_variety_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.base_variety_id_seq OWNED BY public.base_variety.id;


--
-- Name: biz_alert; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_alert (
    id bigint NOT NULL,
    alert_no character varying(32) NOT NULL,
    alert_type character varying(32) NOT NULL,
    biz_type character varying(20) NOT NULL,
    biz_id bigint NOT NULL,
    company_ids character varying(200),
    content character varying(500),
    handler_remark character varying(500),
    handler_id bigint,
    handled_at timestamp without time zone,
    status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.biz_alert OWNER TO postgres;

--
-- Name: biz_alert_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_alert_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_alert_id_seq OWNER TO postgres;

--
-- Name: biz_alert_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_alert_id_seq OWNED BY public.biz_alert.id;


--
-- Name: biz_bargain; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_bargain (
    id bigint NOT NULL,
    quote_id bigint NOT NULL,
    inquiry_id bigint NOT NULL,
    round_no integer DEFAULT 1 NOT NULL,
    initiator character varying(20) NOT NULL,
    price numeric(18,2),
    quantity numeric(18,3),
    delivery_date date,
    settle_type character varying(32),
    extra_terms character varying(500),
    status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.biz_bargain OWNER TO postgres;

--
-- Name: biz_bargain_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_bargain_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_bargain_id_seq OWNER TO postgres;

--
-- Name: biz_bargain_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_bargain_id_seq OWNED BY public.biz_bargain.id;


--
-- Name: biz_contract; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_contract (
    id bigint NOT NULL,
    contract_no character varying(32) NOT NULL,
    order_id bigint NOT NULL,
    version integer DEFAULT 1,
    signature_type character varying(20) DEFAULT 'PLATFORM_CONFIRM'::character varying,
    file_url character varying(500),
    file_hash character varying(64),
    buyer_sign_at timestamp without time zone,
    buyer_sign_user bigint,
    buyer_sign_ip character varying(64),
    supplier_sign_at timestamp without time zone,
    supplier_sign_user bigint,
    supplier_sign_ip character varying(64),
    void_reason character varying(500),
    status character varying(20) DEFAULT 'PENDING_GENERATE'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    updated_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.biz_contract OWNER TO postgres;

--
-- Name: biz_contract_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_contract_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_contract_id_seq OWNER TO postgres;

--
-- Name: biz_contract_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_contract_id_seq OWNED BY public.biz_contract.id;


--
-- Name: biz_demand; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_demand (
    id bigint NOT NULL,
    demand_no character varying(32) NOT NULL,
    company_id bigint NOT NULL,
    demand_name character varying(50) NOT NULL,
    delivery_type character varying(20) NOT NULL,
    delivery_place character varying(100) NOT NULL,
    expect_arrive_start date NOT NULL,
    expect_arrive_end date NOT NULL,
    price_intent character varying(500),
    settle_type character varying(32) NOT NULL,
    quality_req character varying(500),
    remark character varying(500),
    version integer DEFAULT 1,
    status character varying(20) DEFAULT 'DRAFT'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    updated_by bigint,
    is_deleted smallint DEFAULT 0,
    attachments text
);


ALTER TABLE public.biz_demand OWNER TO postgres;

--
-- Name: biz_demand_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_demand_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_demand_id_seq OWNER TO postgres;

--
-- Name: biz_demand_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_demand_id_seq OWNED BY public.biz_demand.id;


--
-- Name: biz_demand_item; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_demand_item (
    id bigint NOT NULL,
    demand_id bigint NOT NULL,
    variety_id bigint NOT NULL,
    grade numeric(5,2) NOT NULL,
    quantity numeric(18,3) NOT NULL,
    more_less_rate numeric(6,2) DEFAULT 5.00,
    inquired_qty numeric(18,3) DEFAULT 0,
    deal_qty numeric(18,3) DEFAULT 0,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    updated_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.biz_demand_item OWNER TO postgres;

--
-- Name: biz_demand_item_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_demand_item_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_demand_item_id_seq OWNER TO postgres;

--
-- Name: biz_demand_item_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_demand_item_id_seq OWNED BY public.biz_demand_item.id;


--
-- Name: biz_forecast_quote; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_forecast_quote (
    id bigint NOT NULL,
    forecast_no character varying(32) NOT NULL,
    supplier_id bigint NOT NULL,
    variety_id bigint NOT NULL,
    period_type character varying(16) NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    available_qty numeric(18,3) NOT NULL,
    forecast_price numeric(18,2) NOT NULL,
    price_basis character varying(16) DEFAULT 'WET'::character varying,
    delivery_port character varying(100),
    valid_until date,
    remark character varying(500),
    status character varying(20) DEFAULT 'EFFECTIVE'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    updated_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.biz_forecast_quote OWNER TO postgres;

--
-- Name: biz_forecast_quote_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_forecast_quote_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_forecast_quote_id_seq OWNER TO postgres;

--
-- Name: biz_forecast_quote_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_forecast_quote_id_seq OWNED BY public.biz_forecast_quote.id;


--
-- Name: biz_inquiry; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_inquiry (
    id bigint NOT NULL,
    inquiry_no character varying(32) NOT NULL,
    demand_id bigint,
    demand_item_id bigint,
    buyer_id bigint NOT NULL,
    variety_id bigint NOT NULL,
    grade numeric(5,2),
    quantity numeric(18,3) NOT NULL,
    delivery_type character varying(20),
    delivery_place character varying(100),
    expect_arrive_date date,
    settle_type character varying(32),
    deadline timestamp without time zone NOT NULL,
    min_response integer DEFAULT 2,
    inquiry_desc character varying(1000),
    status character varying(20) DEFAULT 'DRAFT'::character varying NOT NULL,
    reveal_snapshot text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    updated_by bigint,
    is_deleted smallint DEFAULT 0,
    sent_at timestamp without time zone
);


ALTER TABLE public.biz_inquiry OWNER TO postgres;

--
-- Name: biz_inquiry_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_inquiry_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_inquiry_id_seq OWNER TO postgres;

--
-- Name: biz_inquiry_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_inquiry_id_seq OWNED BY public.biz_inquiry.id;


--
-- Name: biz_inquiry_invite; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_inquiry_invite (
    id bigint NOT NULL,
    inquiry_id bigint NOT NULL,
    supplier_id bigint NOT NULL,
    status character varying(20) DEFAULT 'INVITED'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.biz_inquiry_invite OWNER TO postgres;

--
-- Name: biz_inquiry_invite_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_inquiry_invite_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_inquiry_invite_id_seq OWNER TO postgres;

--
-- Name: biz_inquiry_invite_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_inquiry_invite_id_seq OWNED BY public.biz_inquiry_invite.id;


--
-- Name: biz_logistics_plan; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_logistics_plan (
    id bigint NOT NULL,
    plan_no character varying(32) NOT NULL,
    order_id bigint NOT NULL,
    org_mode character varying(20) NOT NULL,
    remark character varying(500),
    status character varying(20) DEFAULT 'ACTIVE'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    updated_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.biz_logistics_plan OWNER TO postgres;

--
-- Name: biz_logistics_plan_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_logistics_plan_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_logistics_plan_id_seq OWNER TO postgres;

--
-- Name: biz_logistics_plan_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_logistics_plan_id_seq OWNED BY public.biz_logistics_plan.id;


--
-- Name: biz_order; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_order (
    id bigint NOT NULL,
    order_no character varying(32) NOT NULL,
    inquiry_id bigint,
    quote_id bigint,
    demand_id bigint,
    buyer_id bigint NOT NULL,
    supplier_id bigint NOT NULL,
    variety_id bigint NOT NULL,
    grade numeric(5,2),
    quantity numeric(18,3) NOT NULL,
    more_less_rate numeric(6,2) DEFAULT 5.00,
    unit_price numeric(18,2) NOT NULL,
    amount numeric(18,2) NOT NULL,
    price_basis character varying(16) DEFAULT 'WET'::character varying,
    delivery_type character varying(20),
    delivery_place character varying(100),
    delivery_date date,
    settle_type character varying(32),
    quality_terms character varying(500),
    confirm_deadline timestamp without time zone,
    status character varying(20) DEFAULT 'PENDING_CONFIRM'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    updated_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.biz_order OWNER TO postgres;

--
-- Name: biz_order_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_order_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_order_id_seq OWNER TO postgres;

--
-- Name: biz_order_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_order_id_seq OWNED BY public.biz_order.id;


--
-- Name: biz_payment; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_payment (
    id bigint NOT NULL,
    payment_no character varying(32) NOT NULL,
    settlement_id bigint NOT NULL,
    payer_id bigint NOT NULL,
    amount numeric(18,2) NOT NULL,
    pay_date date NOT NULL,
    pay_desc character varying(500),
    file_url character varying(500),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.biz_payment OWNER TO postgres;

--
-- Name: biz_payment_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_payment_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_payment_id_seq OWNER TO postgres;

--
-- Name: biz_payment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_payment_id_seq OWNED BY public.biz_payment.id;


--
-- Name: biz_quality_check; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_quality_check (
    id bigint NOT NULL,
    check_no character varying(32) NOT NULL,
    order_id bigint NOT NULL,
    arrived_qty numeric(18,3) NOT NULL,
    indicators text,
    conclusion character varying(20) NOT NULL,
    check_desc character varying(500),
    file_url character varying(500),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.biz_quality_check OWNER TO postgres;

--
-- Name: biz_quality_check_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_quality_check_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_quality_check_id_seq OWNER TO postgres;

--
-- Name: biz_quality_check_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_quality_check_id_seq OWNED BY public.biz_quality_check.id;


--
-- Name: biz_quote; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_quote (
    id bigint NOT NULL,
    quote_no character varying(32) NOT NULL,
    inquiry_id bigint NOT NULL,
    supplier_id bigint NOT NULL,
    price numeric(18,2) NOT NULL,
    quantity numeric(18,3) NOT NULL,
    delivery_date date NOT NULL,
    delivery_place character varying(100),
    pay_terms character varying(200),
    quality_commit character varying(300),
    valid_until date,
    remark character varying(300),
    version integer DEFAULT 1,
    status character varying(20) DEFAULT 'SUBMITTED'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    updated_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.biz_quote OWNER TO postgres;

--
-- Name: biz_quote_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_quote_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_quote_id_seq OWNER TO postgres;

--
-- Name: biz_quote_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_quote_id_seq OWNED BY public.biz_quote.id;


--
-- Name: biz_settlement; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_settlement (
    id bigint NOT NULL,
    settle_no character varying(32) NOT NULL,
    order_id bigint NOT NULL,
    settle_qty numeric(18,3) NOT NULL,
    unit_price numeric(18,2) NOT NULL,
    adjust_amount numeric(18,2) DEFAULT 0,
    deduct_amount numeric(18,2) DEFAULT 0,
    total_amount numeric(18,2) NOT NULL,
    settle_desc character varying(500),
    supplier_confirm_at timestamp without time zone,
    buyer_confirm_at timestamp without time zone,
    status character varying(32) DEFAULT 'PENDING_CONFIRM_SUPPLIER'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    updated_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.biz_settlement OWNER TO postgres;

--
-- Name: biz_settlement_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_settlement_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_settlement_id_seq OWNER TO postgres;

--
-- Name: biz_settlement_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_settlement_id_seq OWNED BY public.biz_settlement.id;


--
-- Name: biz_track_node; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_track_node (
    id bigint NOT NULL,
    biz_type character varying(20) NOT NULL,
    biz_id bigint NOT NULL,
    node_code character varying(32) NOT NULL,
    node_name character varying(64) NOT NULL,
    occur_time timestamp without time zone NOT NULL,
    source character varying(16) NOT NULL,
    remark character varying(500),
    correct_node_id bigint,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint
);


ALTER TABLE public.biz_track_node OWNER TO postgres;

--
-- Name: biz_track_node_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_track_node_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_track_node_id_seq OWNER TO postgres;

--
-- Name: biz_track_node_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_track_node_id_seq OWNED BY public.biz_track_node.id;


--
-- Name: biz_waybill; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.biz_waybill (
    id bigint NOT NULL,
    waybill_no character varying(32) NOT NULL,
    order_id bigint NOT NULL,
    plan_id bigint NOT NULL,
    segment_no character varying(32) NOT NULL,
    carrier_id bigint,
    transport_mode character varying(20) NOT NULL,
    depart_place character varying(100),
    arrive_place character varying(100),
    plan_depart_date date,
    plan_arrive_date date,
    plan_qty numeric(18,3) NOT NULL,
    freight numeric(18,2),
    vehicle_no character varying(50),
    actual_qty numeric(18,3),
    actual_depart_at timestamp without time zone,
    actual_arrive_at timestamp without time zone,
    status character varying(20) DEFAULT 'PENDING_ASSIGN'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    updated_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.biz_waybill OWNER TO postgres;

--
-- Name: biz_waybill_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.biz_waybill_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.biz_waybill_id_seq OWNER TO postgres;

--
-- Name: biz_waybill_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.biz_waybill_id_seq OWNED BY public.biz_waybill.id;


--
-- Name: ent_company; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ent_company (
    id bigint NOT NULL,
    company_name character varying(100) NOT NULL,
    credit_code character varying(18) NOT NULL,
    company_types character varying(64) NOT NULL,
    province character varying(32),
    city character varying(32),
    address character varying(200),
    legal_person character varying(30),
    contact_name character varying(30),
    contact_phone character varying(20),
    contact_email character varying(64),
    business_scope character varying(500),
    bank_name character varying(100),
    bank_account character varying(30),
    audit_status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    audit_remark character varying(500),
    status character varying(20) DEFAULT 'ENABLED'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    updated_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.ent_company OWNER TO postgres;

--
-- Name: ent_company_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ent_company_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.ent_company_id_seq OWNER TO postgres;

--
-- Name: ent_company_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ent_company_id_seq OWNED BY public.ent_company.id;


--
-- Name: ent_qualification; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ent_qualification (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    file_id character varying(64) NOT NULL,
    file_name character varying(200),
    file_type character varying(20) DEFAULT 'BUSINESS_LICENSE'::character varying,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.ent_qualification OWNER TO postgres;

--
-- Name: ent_qualification_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ent_qualification_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.ent_qualification_id_seq OWNER TO postgres;

--
-- Name: ent_qualification_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ent_qualification_id_seq OWNED BY public.ent_qualification.id;


--
-- Name: sys_file; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sys_file (
    id bigint NOT NULL,
    file_id character varying(64) NOT NULL,
    file_name character varying(200) NOT NULL,
    content_type character varying(100),
    size_bytes bigint DEFAULT 0 NOT NULL,
    path character varying(500) NOT NULL,
    company_id bigint,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.sys_file OWNER TO postgres;

--
-- Name: sys_file_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.sys_file_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.sys_file_id_seq OWNER TO postgres;

--
-- Name: sys_file_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.sys_file_id_seq OWNED BY public.sys_file.id;


--
-- Name: sys_message; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sys_message (
    id bigint NOT NULL,
    receiver_company_id bigint NOT NULL,
    title character varying(100) NOT NULL,
    content character varying(500),
    biz_type character varying(20),
    biz_id bigint,
    is_read smallint DEFAULT 0,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.sys_message OWNER TO postgres;

--
-- Name: sys_message_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.sys_message_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.sys_message_id_seq OWNER TO postgres;

--
-- Name: sys_message_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.sys_message_id_seq OWNED BY public.sys_message.id;


--
-- Name: sys_operation_log; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sys_operation_log (
    id bigint NOT NULL,
    user_id bigint,
    company_id bigint,
    biz_type character varying(20),
    biz_id bigint,
    action character varying(64),
    before_value text,
    after_value text,
    ip character varying(64),
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.sys_operation_log OWNER TO postgres;

--
-- Name: sys_operation_log_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.sys_operation_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.sys_operation_log_id_seq OWNER TO postgres;

--
-- Name: sys_operation_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.sys_operation_log_id_seq OWNED BY public.sys_operation_log.id;


--
-- Name: sys_seq; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sys_seq (
    biz_date date NOT NULL,
    prefix character varying(8) NOT NULL,
    cur integer DEFAULT 0 NOT NULL
);


ALTER TABLE public.sys_seq OWNER TO postgres;

--
-- Name: sys_user; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sys_user (
    id bigint NOT NULL,
    company_id bigint,
    username character varying(50) NOT NULL,
    password_hash character varying(100) NOT NULL,
    real_name character varying(30),
    roles character varying(64) NOT NULL,
    status character varying(20) DEFAULT 'ENABLED'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by bigint,
    updated_by bigint,
    is_deleted smallint DEFAULT 0
);


ALTER TABLE public.sys_user OWNER TO postgres;

--
-- Name: sys_user_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.sys_user_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.sys_user_id_seq OWNER TO postgres;

--
-- Name: sys_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.sys_user_id_seq OWNED BY public.sys_user.id;


--
-- Name: base_price id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.base_price ALTER COLUMN id SET DEFAULT nextval('public.base_price_id_seq'::regclass);


--
-- Name: base_variety id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.base_variety ALTER COLUMN id SET DEFAULT nextval('public.base_variety_id_seq'::regclass);


--
-- Name: biz_alert id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_alert ALTER COLUMN id SET DEFAULT nextval('public.biz_alert_id_seq'::regclass);


--
-- Name: biz_bargain id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_bargain ALTER COLUMN id SET DEFAULT nextval('public.biz_bargain_id_seq'::regclass);


--
-- Name: biz_contract id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_contract ALTER COLUMN id SET DEFAULT nextval('public.biz_contract_id_seq'::regclass);


--
-- Name: biz_demand id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_demand ALTER COLUMN id SET DEFAULT nextval('public.biz_demand_id_seq'::regclass);


--
-- Name: biz_demand_item id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_demand_item ALTER COLUMN id SET DEFAULT nextval('public.biz_demand_item_id_seq'::regclass);


--
-- Name: biz_forecast_quote id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_forecast_quote ALTER COLUMN id SET DEFAULT nextval('public.biz_forecast_quote_id_seq'::regclass);


--
-- Name: biz_inquiry id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_inquiry ALTER COLUMN id SET DEFAULT nextval('public.biz_inquiry_id_seq'::regclass);


--
-- Name: biz_inquiry_invite id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_inquiry_invite ALTER COLUMN id SET DEFAULT nextval('public.biz_inquiry_invite_id_seq'::regclass);


--
-- Name: biz_logistics_plan id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_logistics_plan ALTER COLUMN id SET DEFAULT nextval('public.biz_logistics_plan_id_seq'::regclass);


--
-- Name: biz_order id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_order ALTER COLUMN id SET DEFAULT nextval('public.biz_order_id_seq'::regclass);


--
-- Name: biz_payment id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_payment ALTER COLUMN id SET DEFAULT nextval('public.biz_payment_id_seq'::regclass);


--
-- Name: biz_quality_check id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_quality_check ALTER COLUMN id SET DEFAULT nextval('public.biz_quality_check_id_seq'::regclass);


--
-- Name: biz_quote id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_quote ALTER COLUMN id SET DEFAULT nextval('public.biz_quote_id_seq'::regclass);


--
-- Name: biz_settlement id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_settlement ALTER COLUMN id SET DEFAULT nextval('public.biz_settlement_id_seq'::regclass);


--
-- Name: biz_track_node id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_track_node ALTER COLUMN id SET DEFAULT nextval('public.biz_track_node_id_seq'::regclass);


--
-- Name: biz_waybill id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_waybill ALTER COLUMN id SET DEFAULT nextval('public.biz_waybill_id_seq'::regclass);


--
-- Name: ent_company id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ent_company ALTER COLUMN id SET DEFAULT nextval('public.ent_company_id_seq'::regclass);


--
-- Name: ent_qualification id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ent_qualification ALTER COLUMN id SET DEFAULT nextval('public.ent_qualification_id_seq'::regclass);


--
-- Name: sys_file id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sys_file ALTER COLUMN id SET DEFAULT nextval('public.sys_file_id_seq'::regclass);


--
-- Name: sys_message id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sys_message ALTER COLUMN id SET DEFAULT nextval('public.sys_message_id_seq'::regclass);


--
-- Name: sys_operation_log id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sys_operation_log ALTER COLUMN id SET DEFAULT nextval('public.sys_operation_log_id_seq'::regclass);


--
-- Name: sys_user id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sys_user ALTER COLUMN id SET DEFAULT nextval('public.sys_user_id_seq'::regclass);


--
-- Name: base_price base_price_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.base_price
    ADD CONSTRAINT base_price_pkey PRIMARY KEY (id);


--
-- Name: base_variety base_variety_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.base_variety
    ADD CONSTRAINT base_variety_pkey PRIMARY KEY (id);


--
-- Name: biz_alert biz_alert_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_alert
    ADD CONSTRAINT biz_alert_pkey PRIMARY KEY (id);


--
-- Name: biz_bargain biz_bargain_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_bargain
    ADD CONSTRAINT biz_bargain_pkey PRIMARY KEY (id);


--
-- Name: biz_contract biz_contract_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_contract
    ADD CONSTRAINT biz_contract_pkey PRIMARY KEY (id);


--
-- Name: biz_demand_item biz_demand_item_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_demand_item
    ADD CONSTRAINT biz_demand_item_pkey PRIMARY KEY (id);


--
-- Name: biz_demand biz_demand_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_demand
    ADD CONSTRAINT biz_demand_pkey PRIMARY KEY (id);


--
-- Name: biz_forecast_quote biz_forecast_quote_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_forecast_quote
    ADD CONSTRAINT biz_forecast_quote_pkey PRIMARY KEY (id);


--
-- Name: biz_inquiry_invite biz_inquiry_invite_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_inquiry_invite
    ADD CONSTRAINT biz_inquiry_invite_pkey PRIMARY KEY (id);


--
-- Name: biz_inquiry biz_inquiry_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_inquiry
    ADD CONSTRAINT biz_inquiry_pkey PRIMARY KEY (id);


--
-- Name: biz_logistics_plan biz_logistics_plan_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_logistics_plan
    ADD CONSTRAINT biz_logistics_plan_pkey PRIMARY KEY (id);


--
-- Name: biz_order biz_order_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_order
    ADD CONSTRAINT biz_order_pkey PRIMARY KEY (id);


--
-- Name: biz_payment biz_payment_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_payment
    ADD CONSTRAINT biz_payment_pkey PRIMARY KEY (id);


--
-- Name: biz_quality_check biz_quality_check_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_quality_check
    ADD CONSTRAINT biz_quality_check_pkey PRIMARY KEY (id);


--
-- Name: biz_quote biz_quote_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_quote
    ADD CONSTRAINT biz_quote_pkey PRIMARY KEY (id);


--
-- Name: biz_settlement biz_settlement_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_settlement
    ADD CONSTRAINT biz_settlement_pkey PRIMARY KEY (id);


--
-- Name: biz_track_node biz_track_node_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_track_node
    ADD CONSTRAINT biz_track_node_pkey PRIMARY KEY (id);


--
-- Name: biz_waybill biz_waybill_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_waybill
    ADD CONSTRAINT biz_waybill_pkey PRIMARY KEY (id);


--
-- Name: ent_company ent_company_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ent_company
    ADD CONSTRAINT ent_company_pkey PRIMARY KEY (id);


--
-- Name: ent_qualification ent_qualification_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ent_qualification
    ADD CONSTRAINT ent_qualification_pkey PRIMARY KEY (id);


--
-- Name: sys_file sys_file_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sys_file
    ADD CONSTRAINT sys_file_pkey PRIMARY KEY (id);


--
-- Name: sys_message sys_message_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sys_message
    ADD CONSTRAINT sys_message_pkey PRIMARY KEY (id);


--
-- Name: sys_operation_log sys_operation_log_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sys_operation_log
    ADD CONSTRAINT sys_operation_log_pkey PRIMARY KEY (id);


--
-- Name: sys_seq sys_seq_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sys_seq
    ADD CONSTRAINT sys_seq_pkey PRIMARY KEY (biz_date, prefix);


--
-- Name: sys_user sys_user_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sys_user
    ADD CONSTRAINT sys_user_pkey PRIMARY KEY (id);


--
-- Name: biz_alert uk_alert_no; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_alert
    ADD CONSTRAINT uk_alert_no UNIQUE (alert_no);


--
-- Name: biz_quality_check uk_check_no; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_quality_check
    ADD CONSTRAINT uk_check_no UNIQUE (check_no);


--
-- Name: base_variety uk_code; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.base_variety
    ADD CONSTRAINT uk_code UNIQUE (variety_code);


--
-- Name: biz_contract uk_contract_no; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_contract
    ADD CONSTRAINT uk_contract_no UNIQUE (contract_no);


--
-- Name: ent_company uk_credit_code; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ent_company
    ADD CONSTRAINT uk_credit_code UNIQUE (credit_code);


--
-- Name: biz_demand uk_demand_no; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_demand
    ADD CONSTRAINT uk_demand_no UNIQUE (demand_no);


--
-- Name: sys_file uk_file_id; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sys_file
    ADD CONSTRAINT uk_file_id UNIQUE (file_id);


--
-- Name: biz_forecast_quote uk_forecast_no; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_forecast_quote
    ADD CONSTRAINT uk_forecast_no UNIQUE (forecast_no);


--
-- Name: biz_inquiry uk_inquiry_no; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_inquiry
    ADD CONSTRAINT uk_inquiry_no UNIQUE (inquiry_no);


--
-- Name: biz_inquiry_invite uk_inv; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_inquiry_invite
    ADD CONSTRAINT uk_inv UNIQUE (inquiry_id, supplier_id);


--
-- Name: biz_order uk_order_no; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_order
    ADD CONSTRAINT uk_order_no UNIQUE (order_no);


--
-- Name: biz_payment uk_payment_no; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_payment
    ADD CONSTRAINT uk_payment_no UNIQUE (payment_no);


--
-- Name: biz_logistics_plan uk_plan_no; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_logistics_plan
    ADD CONSTRAINT uk_plan_no UNIQUE (plan_no);


--
-- Name: biz_quote uk_quote_no; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_quote
    ADD CONSTRAINT uk_quote_no UNIQUE (quote_no);


--
-- Name: biz_settlement uk_settle_no; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_settlement
    ADD CONSTRAINT uk_settle_no UNIQUE (settle_no);


--
-- Name: sys_user uk_username; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sys_user
    ADD CONSTRAINT uk_username UNIQUE (username);


--
-- Name: base_price uk_variety_date; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.base_price
    ADD CONSTRAINT uk_variety_date UNIQUE (variety_id, price_date);


--
-- Name: biz_waybill uk_waybill_no; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.biz_waybill
    ADD CONSTRAINT uk_waybill_no UNIQUE (waybill_no);


--
-- Name: idx_alert_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_alert_status ON public.biz_alert USING btree (status);


--
-- Name: idx_audit; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_audit ON public.ent_company USING btree (audit_status);


--
-- Name: idx_bargain_quote; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_bargain_quote ON public.biz_bargain USING btree (quote_id);


--
-- Name: idx_buyer; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_buyer ON public.biz_inquiry USING btree (buyer_id);


--
-- Name: idx_company; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_company ON public.biz_demand USING btree (company_id);


--
-- Name: idx_contract_order; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_contract_order ON public.biz_contract USING btree (order_id);


--
-- Name: idx_demand; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_demand ON public.biz_demand_item USING btree (demand_id);


--
-- Name: idx_inquiry_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_inquiry_status ON public.biz_inquiry USING btree (status);


--
-- Name: idx_log_biz; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_log_biz ON public.sys_operation_log USING btree (biz_type, biz_id);


--
-- Name: idx_log_time; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_log_time ON public.sys_operation_log USING btree (created_at);


--
-- Name: idx_log_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_log_user ON public.sys_operation_log USING btree (user_id);


--
-- Name: idx_order_buyer; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_order_buyer ON public.biz_order USING btree (buyer_id);


--
-- Name: idx_order_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_order_status ON public.biz_order USING btree (status);


--
-- Name: idx_order_supplier; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_order_supplier ON public.biz_order USING btree (supplier_id);


--
-- Name: idx_quote_inquiry; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_quote_inquiry ON public.biz_quote USING btree (inquiry_id);


--
-- Name: idx_quote_supplier; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_quote_supplier ON public.biz_quote USING btree (supplier_id);


--
-- Name: idx_settle_order; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_settle_order ON public.biz_settlement USING btree (order_id);


--
-- Name: idx_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_status ON public.biz_demand USING btree (status);


--
-- Name: idx_track_biz; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_track_biz ON public.biz_track_node USING btree (biz_type, biz_id);


--
-- Name: idx_track_time; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_track_time ON public.biz_track_node USING btree (occur_time);


--
-- Name: idx_user_company; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_company ON public.sys_user USING btree (company_id);


--
-- Name: idx_waybill_carrier; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_waybill_carrier ON public.biz_waybill USING btree (carrier_id);


--
-- Name: idx_waybill_order; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_waybill_order ON public.biz_waybill USING btree (order_id);


--
-- Name: uk_alert_dedup; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX uk_alert_dedup ON public.biz_alert USING btree (alert_type, biz_type, biz_id) WHERE (((status)::text = ANY ((ARRAY['PENDING'::character varying, 'PROCESSING'::character varying])::text[])) AND (is_deleted = 0));


--
-- PostgreSQL database dump complete
--

\unrestrict Lb9KCfoXWj2kJULcRfyQrfbiHIqI2jFgsnsx78LK3zdukJ1VU1nKZE0iFrJpifh

