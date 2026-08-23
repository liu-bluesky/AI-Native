import json
import unittest

from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from lark_oapi.core import JSON

from feishu_sdk_listener import message_payload_has_signal, normalize_message_event


MESSAGE = {
    "message_id": "om_test",
    "chat_id": "oc_test",
    "chat_type": "p2p",
    "message_type": "text",
    "content": json.dumps({"text": "hello"}, ensure_ascii=False),
    "mentions": [],
}

EVENT = {
    "sender": {
        "sender_id": {"open_id": "ou_test"},
        "sender_type": "user",
        "tenant_key": "tenant_test",
    },
    "message": MESSAGE,
}


class NormalizeMessageEventTests(unittest.TestCase):
    def test_normalizes_dict_event(self):
        payload = normalize_message_event(
            {
                "schema": "2.0",
                "header": {
                    "event_id": "evt_test",
                    "event_type": "im.message.receive_v1",
                },
                "event": EVENT,
            },
            "connector_test",
        )

        self.assertEqual(payload["event_id"], "evt_test")
        self.assertEqual(payload["message_id"], "om_test")
        self.assertEqual(payload["chat_id"], "oc_test")
        self.assertEqual(payload["chat_type"], "p2p")
        self.assertEqual(payload["sender_id"], "ou_test")
        self.assertEqual(payload["content"], "hello")

    def test_normalizes_sdk_event_object(self):
        sdk_event = JSON.unmarshal(
            json.dumps(
                {
                    "schema": "2.0",
                    "header": {
                        "event_id": "evt_test",
                        "event_type": "im.message.receive_v1",
                    },
                    "event": EVENT,
                }
            ),
            P2ImMessageReceiveV1,
        )

        payload = normalize_message_event(sdk_event, "connector_test")

        self.assertEqual(payload["event_id"], "evt_test")
        self.assertEqual(payload["message_id"], "om_test")
        self.assertEqual(payload["chat_id"], "oc_test")
        self.assertEqual(payload["chat_type"], "p2p")
        self.assertEqual(payload["sender_id"], "ou_test")
        self.assertEqual(payload["content"], "hello")

    def test_normalizes_inner_sdk_event_object(self):
        sdk_event = JSON.unmarshal(
            json.dumps(
                {
                    "schema": "2.0",
                    "header": {
                        "event_id": "evt_test",
                        "event_type": "im.message.receive_v1",
                    },
                    "event": EVENT,
                }
            ),
            P2ImMessageReceiveV1,
        )

        payload = normalize_message_event(sdk_event.event, "connector_test")

        self.assertEqual(payload["message_id"], "om_test")
        self.assertEqual(payload["chat_id"], "oc_test")
        self.assertEqual(payload["chat_type"], "p2p")
        self.assertEqual(payload["sender_id"], "ou_test")
        self.assertEqual(payload["content"], "hello")

    def test_normalizes_camel_case_dict(self):
        payload = normalize_message_event(
            {
                "sender": {"senderId": {"openId": "ou_test"}},
                "message": {
                    "messageId": "om_test",
                    "chatId": "oc_test",
                    "chatType": "group",
                    "messageType": "text",
                    "content": '{"text":"hello"}',
                },
            },
            "connector_test",
        )

        self.assertEqual(payload["message_id"], "om_test")
        self.assertEqual(payload["chat_id"], "oc_test")
        self.assertEqual(payload["chat_type"], "group")
        self.assertEqual(payload["sender_id"], "ou_test")
        self.assertEqual(payload["content"], "hello")

    def test_empty_message_payload_has_no_signal(self):
        self.assertFalse(message_payload_has_signal({
            "event_id": "",
            "message_id": "",
            "chat_id": "",
            "chat_type": "",
            "content": "",
        }))
        self.assertTrue(message_payload_has_signal({"chat_id": "oc_test"}))


if __name__ == "__main__":
    unittest.main()
