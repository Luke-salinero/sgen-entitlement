import unittest
from unittest.mock import patch

# Adjust this import to match your project structure:
# e.g., from app.core import auth as auth_module
from app.core import auth as auth_module


class TestAuthenticateBearer(unittest.TestCase):
    """
    Tests for _authenticate_bearer(auth_header).

    These tests focus on parsing the Authorization header, correctly calling jwt.decode,
    and handling decoded claim edge cases.
    """

    def test_rejects_non_bearer_scheme(self):
        """Use case: Caller sends Authorization with the wrong scheme (e.g., Basic).
        If this fails, unsupported schemes might be mistakenly accepted."""
        with self.assertRaises(auth_module.InvalidAuthenticationError) as ctx:
            auth_module._authenticate_bearer("Basic abc.def.ghi")
        self.assertIn("Unsupported authorization scheme", str(ctx.exception))

    def test_rejects_missing_token_after_bearer(self):
        """Use case: Caller sends 'Bearer ' with no token.
        If this fails, empty credentials could pass deeper into the system."""
        with self.assertRaises(auth_module.InvalidAuthenticationError) as ctx:
            auth_module._authenticate_bearer("Bearer ")
        self.assertIn("Empty bearer token", str(ctx.exception))

    def test_rejects_whitespace_only_token(self):
        """Use case: Caller sends a token that is only whitespace. If this fails, you
        may attempt to decode invalid input and leak confusing errors upstream."""
        with self.assertRaises(auth_module.InvalidAuthenticationError) as ctx:
            auth_module._authenticate_bearer("Bearer     ")
        self.assertIn("Empty bearer token", str(ctx.exception))

    @patch("app.core.auth.jwt.decode")
    def test_calls_jwt_decode_with_expected_parameters(self, mock_decode):
        """Use case: Ensures jwt.decode is called with expected key, algorithm,
        audience, and issuer. If this fails, tokens might be verified against
        the wrong trust settings."""
        mock_decode.return_value = {"sub": "123", "email": "user@example.com"}

        auth_module._authenticate_bearer("Bearer some.jwt.token")

        mock_decode.assert_called_once()
        args, kwargs = mock_decode.call_args

        # Positional arg 0 is the token string passed to decode()
        self.assertEqual(args[0], "some.jwt.token")

        # Validate the important decode configuration
        self.assertEqual(kwargs["key"], "public_key")
        self.assertEqual(kwargs["algorithms"], ["RS256"])
        self.assertEqual(kwargs["audience"], "OURAUDIENCE")
        self.assertEqual(kwargs["issuer"], "OURISSUER")

    @patch("app.core.auth.jwt.decode")
    def test_missing_sub_claim_raises_invalid_auth(self, mock_decode):
        """Use case: Token decodes but lacks the required subject claim. If this fails,
        anonymous/invalid identities could be treated as authenticated."""
        mock_decode.return_value = {"email": "user@example.com"}

        with self.assertRaises(auth_module.InvalidAuthenticationError) as ctx:
            auth_module._authenticate_bearer("Bearer valid.token.here")

        self.assertIn("Missing subject in token", str(ctx.exception))

    @patch("app.core.auth.jwt.decode")
    def test_empty_sub_claim_raises_invalid_auth(self, mock_decode):
        """Use case: Token contains sub but it is empty/falsey. If this fails, you may
        create identities with meaningless subject IDs."""
        mock_decode.return_value = {"sub": "", "email": "user@example.com"}

        with self.assertRaises(auth_module.InvalidAuthenticationError) as ctx:
            auth_module._authenticate_bearer("Bearer valid.token.here")

        self.assertIn("Missing subject in token", str(ctx.exception))

    @patch("app.core.auth.jwt.decode")
    def test_identity_is_built_correctly(self, mock_decode):
        """Use case: Valid token should create a complete Identity object.
        If this fails, downstream services may break due to
        missing or malformed identity fields."""
        claims = {"sub": 456, "email": "dev@example.com", "role": "tester"}
        mock_decode.return_value = claims

        identity = auth_module._authenticate_bearer("Bearer token.value")

        self.assertIsInstance(identity, auth_module.Identity)
        self.assertEqual(identity.subject_id, "456")  # cast to str by your code
        self.assertEqual(identity.account_name, "dev@example.com")
        self.assertEqual(identity.provider, "bearer")
        self.assertEqual(identity.raw_claims, claims)

    @patch("app.core.auth.jwt.decode")
    def test_email_claim_optional(self, mock_decode):
        """Use case: JWT may not include email, but auth should still succeed. If this
        fails, tokens without optional metadata will be rejected incorrectly."""
        mock_decode.return_value = {"sub": "abc"}  # no email

        identity = auth_module._authenticate_bearer("Bearer token.value")

        self.assertEqual(identity.subject_id, "abc")
        self.assertIsNone(identity.account_name)

    @patch("app.core.auth.jwt.decode")
    def test_decode_exception_bubbles_up_currently(self, mock_decode):
        """
        Use case: jwt.decode may raise (expired token, invalid signature, bad aud/iss).
        If this fails, unexpected exceptions may be hidden or misclassified,
        making debugging and security responses inconsistent.
        """
        mock_decode.side_effect = Exception("decode failed")

        with self.assertRaises(Exception) as ctx:
            auth_module._authenticate_bearer("Bearer token.value")

        self.assertIn("decode failed", str(ctx.exception))

    def test_case_sensitive_bearer_prefix(self):
        """Use case: 'bearer ' (lowercase) is not accepted by your implementation.
        If this fails unexpectedly, you may accidentally accept
        non-standard formats you didn’t intend."""
        with self.assertRaises(auth_module.InvalidAuthenticationError) as ctx:
            auth_module._authenticate_bearer("bearer token")
        self.assertIn("Unsupported authorization scheme", str(ctx.exception))


class TestAuthenticateRequest(unittest.TestCase):
    """
    Tests for authenticate_request(headers).

    These tests focus on selecting the appropriate
    authentication method based on headers.
    """

    def test_missing_authorization_header_raises_missing_auth(self):
        """Use case: Request without Authorization must be rejected.
        If this fails, unauthenticated requests could reach
        protected endpoints."""
        with self.assertRaises(auth_module.MissingAuthenticationError) as ctx:
            auth_module.authenticate_request({})
        self.assertIn("No supported authentication headers found", str(ctx.exception))
        self.assertEqual(ctx.exception.code, "auth_missing")

    def test_authorization_header_present_calls_bearer_auth(self):
        """Use case: When Authorization header is present, bearer auth should run.
        If this fails, valid requests may be
        rejected or routed incorrectly."""
        headers = {"Authorization": "Bearer token.value"}

        with patch.object(auth_module, "_authenticate_bearer") as mock_bearer:
            mock_bearer.return_value = auth_module.Identity(
                subject_id="1",
                account_name=None,
                provider="bearer",
                raw_claims={"sub": "1"},
            )
            identity = auth_module.authenticate_request(headers)

            mock_bearer.assert_called_once_with("Bearer token.value")
            self.assertEqual(identity.subject_id, "1")

    def test_authorization_header_key_is_case_sensitive_in_mapping(self):
        """Use case: Your current code expects 'Authorization' exactly; 'authorization'
        won’t be found in a plain dict. If this fails, you may think you're supporting
        case-insensitive headers when you are not."""
        headers = {
            "authorization": "Bearer token.value"
        }  # lower-case key in plain dict

        with self.assertRaises(auth_module.MissingAuthenticationError):
            auth_module.authenticate_request(headers)


class TestAuthBulk(unittest.TestCase):
    """
    Quantity-focused tests: many combinations of headers, bearer formatting, and claims.
    Uses subTest() so each combination reports cleanly.
    """

    @patch("app.core.auth.jwt.decode")
    def test_bulk_bearer_header_parsing_cases(self, mock_decode):
        """
        Bulk cases around how the Authorization header
        is parsed before decode is attempted. If any of these fail,
        your service may accept malformed headers or reject valid ones unexpectedly.
        """
        mock_decode.return_value = {"sub": "1"}  # only used when header parsing passes

        cases = [
            # (name, auth_header, should_raise, expected_error_substring)
            (
                "non_bearer_scheme_basic",
                "Basic abc",
                True,
                "Unsupported authorization scheme",
            ),
            (
                "non_bearer_scheme_token",
                "Token abc",
                True,
                "Unsupported authorization scheme",
            ),
            (
                "lowercase_bearer",
                "bearer abc",
                True,
                "Unsupported authorization scheme",
            ),
            ("bearer_no_token", "Bearer ", True, "Empty bearer token"),
            ("bearer_only_spaces", "Bearer      ", True, "Empty bearer token"),
            ("bearer_token_trimmed", "Bearer   abc.def   ", False, None),
            ("bearer_token_plain", "Bearer abc.def", False, None),
        ]

        for name, header, should_raise, msg in cases:
            with self.subTest(case=name, header=header):
                if should_raise:
                    with self.assertRaises(
                        auth_module.InvalidAuthenticationError
                    ) as ctx:
                        auth_module._authenticate_bearer(header)
                    self.assertIn(msg, str(ctx.exception))
                else:
                    ident = auth_module._authenticate_bearer(header)
                    self.assertEqual(ident.subject_id, "1")
                    self.assertEqual(ident.provider, "bearer")

        # Sanity: decode should only be called for the non-raising cases (2 cases above)
        self.assertEqual(mock_decode.call_count, 2)

    @patch("app.core.auth.jwt.decode")
    def test_bulk_claim_shapes_for_identity_construction(self, mock_decode):
        """
        Bulk cases for decoded claim variations (types, optional email, etc.).
        If any of these fail, you may produce inconsistent
        identity objects or accept invalid subjects.
        """
        claim_cases = [
            # (name, claims, should_raise, expected_subject_id, expected_email)
            (
                "sub_int_email_present",
                {"sub": 123, "email": "a@b.com"},
                False,
                "123",
                "a@b.com",
            ),
            (
                "sub_str_email_present",
                {"sub": "user-1", "email": "a@b.com"},
                False,
                "user-1",
                "a@b.com",
            ),
            (
                "sub_uuidish_no_email",
                {"sub": "550e8400-e29b-41d4-a716-446655440000"},
                False,
                "550e8400-e29b-41d4-a716-446655440000",
                None,
            ),
            ("sub_str_email_none", {"sub": "x", "email": None}, False, "x", None),
            ("sub_missing", {"email": "a@b.com"}, True, None, None),
            ("sub_empty_string", {"sub": "", "email": "a@b.com"}, True, None, None),
            ("sub_none", {"sub": None, "email": "a@b.com"}, True, None, None),
            (
                "sub_zero_int",
                {"sub": 0, "email": "a@b.com"},
                True,
                None,
                None,
            ),  # 0 is falsey → rejected by your code
        ]

        for name, claims, should_raise, expected_sub, expected_email in claim_cases:
            with self.subTest(case=name, claims=claims):
                mock_decode.return_value = claims

                if should_raise:
                    with self.assertRaises(
                        auth_module.InvalidAuthenticationError
                    ) as ctx:
                        auth_module._authenticate_bearer("Bearer good.token")
                    self.assertIn("Missing subject in token", str(ctx.exception))
                else:
                    ident = auth_module._authenticate_bearer("Bearer good.token")
                    self.assertEqual(ident.subject_id, expected_sub)
                    self.assertEqual(ident.account_name, expected_email)
                    self.assertEqual(ident.raw_claims, claims)

    @patch("app.core.auth.jwt.decode")
    def test_bulk_authenticate_request_header_combinations(self, mock_decode):
        """
        Bulk cases for authenticate_request(headers) with various header dict shapes.
        If any of these fail, the gateway could be sending
        headers that your service silently ignores.
        """
        mock_decode.return_value = {"sub": "99", "email": "bulk@example.com"}

        cases = [
            # (name, headers, should_raise, expected_exception_type)
            ("no_headers", {}, True, auth_module.MissingAuthenticationError),
            (
                "wrong_header_key_lowercase",
                {"authorization": "Bearer t"},
                True,
                auth_module.MissingAuthenticationError,
            ),
            (
                "wrong_header_key_other",
                {"Auth": "Bearer t"},
                True,
                auth_module.MissingAuthenticationError,
            ),
            ("authorization_present_valid", {"Authorization": "Bearer t"}, False, None),
            (
                "authorization_present_invalid_scheme",
                {"Authorization": "Basic t"},
                True,
                auth_module.InvalidAuthenticationError,
            ),
            (
                "authorization_present_empty_bearer",
                {"Authorization": "Bearer "},
                True,
                auth_module.InvalidAuthenticationError,
            ),
        ]

        for name, headers, should_raise, exc_type in cases:
            with self.subTest(case=name, headers=headers):
                if should_raise:
                    with self.assertRaises(exc_type):
                        auth_module.authenticate_request(headers)
                else:
                    ident = auth_module.authenticate_request(headers)
                    self.assertEqual(ident.subject_id, "99")

    @patch("app.core.auth.jwt.decode")
    def test_bulk_decode_failures_bubble_up_current_behavior(self, mock_decode):
        """
        Quantity tests for different decode error types.
        Your current auth.py lets decode exceptions bubble up; if this fails,
        behavior changed and tests should be updated.
        """
        error_cases = [
            ("generic_exception", Exception("decode failed")),
            ("value_error", ValueError("bad token")),
            ("runtime_error", RuntimeError("issuer mismatch")),
        ]

        for name, exc in error_cases:
            with self.subTest(case=name, exc_type=type(exc).__name__):
                mock_decode.side_effect = exc
                with self.assertRaises(type(exc)):
                    auth_module._authenticate_bearer("Bearer token.value")

        # reset side effect so it doesn't leak into other tests
        mock_decode.side_effect = None


if __name__ == "__main__":
    unittest.main()
