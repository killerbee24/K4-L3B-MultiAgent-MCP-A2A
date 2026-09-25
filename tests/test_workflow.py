from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from student_agent.contracts import Contracts
from student_agent.trace import TraceWriter
from student_agent.workflow import solve_case


class FakeGateway:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.calls: list[str] = []

    async def call(self, tool_name: str, *, case_id: str, **arguments: str) -> dict[str, Any]:
        self.calls.append(tool_name)
        value = self.data.get(tool_name, {})
        if isinstance(value, Exception):
            raise value
        domain = {
            "get_order": "order",
            "get_customer_history": "customer",
            "get_order_items": "item",
            "get_product_context": "product",
            "get_shipment_summary": "shipment",
            "get_order_payments": "payment",
            "get_policy": "policy",
        }.get(tool_name, "order")
        return {
            "evidence_ref": f"ev_{len(self.calls):024d}",
            "domain": domain,
            "data": value,
        }


class FakeTrace:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, **event: Any) -> None:
        self.events.append(event)


def make_case(topic: str) -> dict[str, Any]:
    return {
        "case_id": "L3B_TEST_001",
        "customer_request": {
            "claimed_order_id": "order-1",
            "claims": [
                {"claim_id": "claim-a", "topic": topic},
                {"claim_id": "claim-b", "topic": "requested_full_refund"},
            ],
        },
        "candidate_order_ids": ["order-1", "candidate-fake"],
        "investigation_scope": {"include_product_context": False},
        "policy_version": "EC_POLICY_V2",
    }


def make_data(topic: str) -> dict[str, Any]:
    return {
        "get_order": {"order_id": "order-1", "order_status": "delivered"},
        "get_customer_history": {
            "customer_unique_id": "cust-1",
            "orders": [{"order_id": "order-1"}],
        },
        "get_order_items": [
            {
                "order_item_id": "item-1",
                "seller_id": "seller-1",
                "price": "80.00",
                "freight_value": "20.00",
            }
        ],
        "get_product_context": [],
        "get_shipment_summary": {
            "order_status": "delivered",
            "delivered_carrier_at": "2018-01-03",
            "delivered_customer_at": "2018-01-05",
            "estimated_delivery_at": "2018-01-06",
            "shipping_limits": [],
            "events": [],
        },
        "get_order_payments": [
            {"payment_sequential": 1, "payment_type": "credit_card", "payment_value": "100.00"}
        ],
        "get_policy": {
            "rules": {
                topic: {
                    "case_status": "needs_investigation"
                    if topic == "refund_pending"
                    else "action_required",
                    "recommended_action": "monitor_refund"
                    if topic == "refund_pending"
                    else "issue_refund",
                    "refund_brl": 0 if topic == "refund_pending" else 100,
                    "responsible_parties": [{"party_type": "payment_provider", "party_id": None}],
                },
                "unsupported_claim": {
                    "case_status": "no_action",
                    "recommended_action": "document_no_action",
                    "refund_brl": 0,
                    "responsible_parties": [{"party_type": "customer", "party_id": None}],
                },
                "valid_split_payment": {
                    "case_status": "no_action",
                    "recommended_action": "document_no_action",
                    "refund_brl": 0,
                    "responsible_parties": [{"party_type": "customer", "party_id": None}],
                },
                "late_delivery_logistics": {
                    "case_status": "action_required",
                    "recommended_action": "refund_freight",
                    "refund_brl": 16.0,
                    "responsible_parties": [{"party_type": "logistics_provider", "party_id": None}],
                },
            }
        },
    }


def run_case(case: dict[str, Any], data: dict[str, Any]) -> tuple[dict[str, Any], FakeGateway]:
    gateway = FakeGateway(data)
    output = asyncio.run(solve_case(case, gateway, FakeTrace()))  # type: ignore[arg-type]
    root = Path(__file__).resolve().parents[1]
    Contracts(root / "contracts" / "schemas").validate_output(output, "test output")
    return output, gateway


def test_refund_pending_uses_standard_payments_call() -> None:
    output, gateway = run_case(make_case("refund_pending"), make_data("refund_pending"))
    assert output["assessment"]["primary_issue"] == "refund_pending"
    assert output["payment_analysis"]["verdict"] == "refund_pending"
    assert output["payment_analysis"]["refunded_total_brl"] == 0
    assert "get_order_payments" in gateway.calls


def test_split_payment_is_not_duplicate_capture() -> None:
    data = make_data("valid_split_payment")
    data["get_order_items"].append(dict(data["get_order_items"][0]))
    data["get_order_payments"] = [
        {"payment_sequential": 1, "payment_type": "credit_card", "payment_value": "60.00"},
        {"payment_sequential": 2, "payment_type": "voucher", "payment_value": "40.00"},
    ]
    output, gateway = run_case(make_case("valid_split_payment"), data)
    assert output["assessment"]["primary_issue"] == "valid_split_payment"
    assert output["payment_analysis"]["verdict"] == "reconciled"
    assert output["payment_analysis"]["captured_total_brl"] == 100
    assert output["resolution_actions"] == ["document_no_action"]


def test_authoritative_shipping_delay_overrides_unsupported_claim() -> None:
    data = make_data("unsupported_claim")
    data["get_shipment_summary"]["delivered_customer_at"] = "2018-01-08"
    output, _ = run_case(make_case("unsupported_claim"), data)
    assert output["shipment_analysis"]["verdict"] == "logistics_delay"
    assert output["assessment"]["primary_issue"] == "late_delivery_logistics"
    assert output["data_conflicts"][0]["selected_source"] == "carrier_tracking_log"


def test_payment_mismatch_identified() -> None:
    data = make_data("payment_mismatch")
    output, _ = run_case(make_case("payment_mismatch"), data)
    assert output["assessment"]["primary_issue"] == "payment_mismatch"
    assert output["payment_analysis"]["verdict"] == "capture_mismatch"


def test_order_claim_does_not_make_unneeded_tools_call() -> None:
    output, gateway = run_case(make_case("canceled_order_paid"), make_data("canceled_order_paid"))
    assert output["payment_analysis"]["refunded_total_brl"] == 0
    assert "get_payment_timeline" not in gateway.calls
    assert "get_refund_timeline" not in gateway.calls


def test_duplicate_charge_detected() -> None:
    data = make_data("duplicate_charge")
    data["get_order_payments"] = [
        {"payment_sequential": 1, "payment_type": "credit_card", "payment_value": "50.00"},
        {"payment_sequential": 1, "payment_type": "credit_card", "payment_value": "50.00"},
    ]
    output, gateway = run_case(make_case("duplicate_charge"), data)
    assert output["assessment"]["primary_issue"] == "duplicate_charge"
    assert output["payment_analysis"]["verdict"] == "duplicate_capture"


def test_trace_events_match_public_contract(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    trace_path = tmp_path / "trace.jsonl"
    trace = TraceWriter(trace_path, contracts)
    output = asyncio.run(
        solve_case(make_case("refund_pending"), FakeGateway(make_data("refund_pending")), trace)
    )
    contracts.validate_output(output, "test output")
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert any(event["event_type"] == "verification_completed" for event in events)
    assert any(event["event_type"] == "tool_result_consumed" for event in events)
