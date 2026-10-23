import unittest
import os
import json
from app.database import init_db, get_db
from app.services.sm2_service import calculate_sm2
from app.services.gemini_service import analyze_filler_words_heuristics
from fastapi.testclient import TestClient
from app.main import app

class TestKua(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def test_sm2_algorithm(self):
        rep, ef, interval, next_iso = calculate_sm2(grade=5, repetitions=0, easiness_factor=2.5, interval_days=0)
        self.assertEqual(rep, 1)
        self.assertEqual(interval, 1)
        self.assertGreaterEqual(ef, 2.5)

        rep2, ef2, interval2, _ = calculate_sm2(grade=4, repetitions=rep, easiness_factor=ef, interval_days=interval)
        self.assertEqual(rep2, 2)
        self.assertEqual(interval2, 6)

        rep3, ef3, interval3, _ = calculate_sm2(grade=1, repetitions=rep2, easiness_factor=ef2, interval_days=interval2)
        self.assertEqual(rep3, 0)
        self.assertEqual(interval3, 1)

    def test_filler_words_heuristics(self):
        sample_speech = "Bueno, eh, la memoria virtual es, o sea, un espacio lógico... este... mayor que la RAM."
        res = analyze_filler_words_heuristics(sample_speech)
        self.assertGreaterEqual(res["count"], 3)
        self.assertIn("eh", res["words"])
        self.assertIn("este", res["words"])
        self.assertIn("<mark", res["highlighted_html"])

    def test_api_status_and_quokka_mascot(self):
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["app_name"], "Kua")
        self.assertEqual(data["mascot"], "Quokka")
        self.assertEqual(data["primary_color"], "#0083B0")

    def test_auth_registration_and_login(self):
        import time
        unique_handle = f"student_{int(time.time())}"
        reg_payload = {
            "display_name": "Ana Morales",
            "username": unique_handle,
            "email": f"{unique_handle}@uni.edu",
            "password": "seguraPassword123",
            "university": "Universidad Central",
            "career": "Ingeniería de Software",
            "semester": "6to Semestre"
        }
        reg_res = self.client.post("/api/auth/register", json=reg_payload)
        self.assertEqual(reg_res.status_code, 200)
        reg_data = reg_res.json()
        self.assertIn("user", reg_data)
        self.assertEqual(reg_data["user"]["username"], unique_handle)
        self.assertEqual(reg_data["user"]["university"], "Universidad Central")
        self.assertEqual(reg_data["user"]["fruits_count"], 6)

        # Login test
        login_res = self.client.post("/api/auth/login", json={
            "username_or_email": unique_handle,
            "password": "seguraPassword123"
        })
        self.assertEqual(login_res.status_code, 200)
        login_data = login_res.json()
        self.assertEqual(login_data["user"]["username"], unique_handle)

    def test_quokka_feeding_and_fruits_reward(self):
        # 1. Get status
        status_res = self.client.get("/api/quokka/status?user_id=1")
        self.assertEqual(status_res.status_code, 200)
        st = status_res.json()
        self.assertIn("fruits_count", st)
        self.assertIn("quokka_happiness", st)

        # 2. Award fruits from an oral session (+2 fruits)
        award_res = self.client.post("/api/quokka/award-fruit?user_id=1", json={"session_type": "oral"})
        self.assertEqual(award_res.status_code, 200)
        aw = award_res.json()
        self.assertEqual(aw["fruits_awarded"], 2)

        # 3. Feed the Quokka
        feed_res = self.client.post("/api/quokka/feed?user_id=1", json={"fruit_type": "fresa"})
        self.assertEqual(feed_res.status_code, 200)
        fed = feed_res.json()
        self.assertTrue(fed["is_happy"])
        self.assertIn("Ñam ñam", fed["message"])

    def test_user_public_profile(self):
        res = self.client.get("/api/users/2/public")
        self.assertEqual(res.status_code, 200)
        profile = res.json()
        self.assertEqual(profile["username"], "sofi_med")
        self.assertIn("public_decks", profile)
        self.assertTrue(len(profile["public_decks"]) >= 1)

    def test_deck_privacy_toggle_and_forum_filter(self):
        # Initial feed
        feed_initial = self.client.get("/api/forum/feed").json()
        initial_count = len(feed_initial)

        # Toggle deck 1 to private (is_public = False)
        toggle_res = self.client.post("/api/decks/1/privacy", json={"is_public": False})
        self.assertEqual(toggle_res.status_code, 200)
        self.assertFalse(toggle_res.json()["is_public"])

        # Feed must strictly exclude deck 1 now
        feed_after_private = self.client.get("/api/forum/feed").json()
        self.assertEqual(len(feed_after_private), initial_count - 1)
        for post in feed_after_private:
            self.assertNotEqual(post["deck_id"], 1)

        # Toggle deck 1 back to public (is_public = True)
        toggle_back = self.client.post("/api/decks/1/privacy", json={"is_public": True})
        self.assertEqual(toggle_back.status_code, 200)
        self.assertTrue(toggle_back.json()["is_public"])

        # Feed must include deck 1 again
        feed_restored = self.client.get("/api/forum/feed").json()
        self.assertEqual(len(feed_restored), initial_count)

    def test_deck_cloning_to_my_library(self):
        # User 3 clones Deck 2 (Sofia's public deck)
        clone_res = self.client.post("/api/decks/2/clone?user_id=3")
        self.assertEqual(clone_res.status_code, 200)
        data = clone_res.json()
        new_deck_id = data["new_deck_id"]

        # Check cloned deck in database
        detail_res = self.client.get(f"/api/decks/{new_deck_id}")
        self.assertEqual(detail_res.status_code, 200)
        deck = detail_res.json()
        self.assertEqual(deck["user_id"], 3)
        self.assertFalse(deck["is_public"])  # Default is private in user's library
        self.assertEqual(deck["cloned_from_id"], 2)
        self.assertTrue(len(deck["flashcards"]) > 0)
        self.assertTrue(len(deck["quiz_questions"]) > 0)

    def test_instagram_forum_comments_and_like(self):
        feed_res = self.client.get("/api/forum/feed?current_user_id=1")
        self.assertEqual(feed_res.status_code, 200)
        posts = feed_res.json()
        self.assertTrue(len(posts) > 0)
        target_post = posts[0]

        # Post a comment
        comment_res = self.client.post(
            f"/api/forum/posts/{target_post['id']}/comments?user_id=1",
            json={"comment_text": "¡Excelente resumen, me sirvió mucho para el examen!"}
        )
        self.assertEqual(comment_res.status_code, 200)
        c_data = comment_res.json()
        self.assertEqual(c_data["comment"]["commenter_username"], "estudiante_kua")

        # Toggle Like
        like_res = self.client.post(f"/api/forum/posts/{target_post['id']}/like?user_id=1")
        self.assertEqual(like_res.status_code, 200)
        self.assertIn("liked", like_res.json())

    def test_oral_session_flow(self):
        res = self.client.get("/api/decks")
        deck_id = res.json()[0]["id"]
        
        start_res = self.client.post("/api/oral/sessions/start", json={"deck_id": deck_id})
        self.assertEqual(start_res.status_code, 200)
        session_data = start_res.json()
        session_id = session_data["session_id"]
        self.assertTrue(len(session_data["questions"]) > 0)
        
        comp_res = self.client.post(f"/api/oral/sessions/{session_id}/complete")
        self.assertEqual(comp_res.status_code, 200)
        summary = comp_res.json()
        self.assertEqual(summary["session_id"], session_id)

    def test_dashboard_stats(self):
        res = self.client.get("/api/dashboard/stats?user_id=1")
        self.assertEqual(res.status_code, 200)
        stats = res.json()
        self.assertIn("total_decks", stats)
        self.assertIn("total_cards", stats)
        self.assertIn("fruits_count", stats)
        self.assertIn("quokka_happiness", stats)
        self.assertIn("timeline", stats)

if __name__ == "__main__":
    unittest.main()
