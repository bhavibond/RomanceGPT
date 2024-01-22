import unittest
from app import app, db, User, Message, generate_romantic_message, get_upcoming_occasions, get_user_preferences, get_recommendations

class AppTestCase(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app = app.test_client()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()

    # Helper function to create a test user
    def create_test_user(self):
        return User(username='testuser', password='testpassword', email='test@example.com')

    # Helper function to log in a test user
    def login_test_user(self):
        return self.app.post('/login', data=dict(
            username='testuser',
            password='testpassword'
        ), follow_redirects=True)

    # Test index route when user is not logged in
    def test_index_route_not_logged_in(self):
        response = self.app.get('/')
        self.assertEqual(response.status_code, 302)  # Redirects to login page

    # Test index route when user is logged in
    def test_index_route_logged_in(self):
        with self.app as client:
            with client.session_transaction() as sess:
                sess['user_id'] = self.create_test_user().id
            response = client.get('/')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Welcome to the Romantic Message App', response.data)

    # Test message generation functionality
    def test_generate_romantic_message(self):
        with self.app as client:
            test_user = self.create_test_user()
            db.session.add(test_user)
            db.session.commit()

            with client.session_transaction() as sess:
                sess['user_id'] = test_user.id

            response = generate_romantic_message('Test Girlfriend', 'Special Moments')
            self.assertIn('girlfriend_name', response)
            self.assertIn('romantic_message', response)
            self.assertIn('timestamp', response)

            message_count = Message.query.count()
            self.assertEqual(message_count, 1)

    # Test upcoming special occasions functionality
    def test_upcoming_special_occasions(self):
        occasions = get_upcoming_occasions()
        self.assertIsInstance(occasions, list)

    # Test user preferences functionality
    def test_user_preferences(self):
        test_user = self.create_test_user()
        db.session.add(test_user)
        db.session.commit()

        user_preferences = get_user_preferences(test_user)
        self.assertIsInstance(user_preferences, dict)

    # Test gift recommendations functionality
    def test_gift_recommendations(self):
        user_preferences = {"favorite_category": "Jewelry", "favorite_color": "Blue"}
        recommendations = get_recommendations(user_preferences)
        self.assertIsInstance(recommendations, list)

    # Test login functionality
    def test_login(self):
        test_user = self.create_test_user()
        db.session.add(test_user)
        db.session.commit()

        response = self.login_test_user()
        self.assertIn(b'Logged in successfully', response.data)

    # Test logout functionality
    def test_logout(self):
        test_user = self.create_test_user()
        db.session.add(test_user)
        db.session.commit()

        self.login_test_user()
        response = self.app.get('/logout', follow_redirects=True)
        self.assertIn(b'You have been logged out', response.data)

    # Test change password functionality
    def test_change_password(self):
        test_user = self.create_test_user()
        db.session.add(test_user)
        db.session.commit()

        self.login_test_user()
        response = self.app.post('/change_password', data=dict(
            new_password='newpassword',
            confirm_password='newpassword'
        ), follow_redirects=True)

        self.assertIn(b'Password changed successfully', response.data)

    # Test feedback submission functionality
    def test_feedback_submission(self):
        test_user = self.create_test_user()
        db.session.add(test_user)
        db.session.commit()

        self.login_test_user()
        response = self.app.post('/submit_feedback', data=dict(
            feedback='This app is amazing!'
        ), follow_redirects=True)

        self.assertIn(b'Thank you for your feedback!', response.data)

if __name__ == '__main__':
    unittest.main()
