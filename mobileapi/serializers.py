from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class MobileTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Same username/password check as the web login form (Django's
    AuthenticationForm via PosLoginView), but rejects a user with no
    UserProfile — every real POS user has one; a bare superuser without a
    profile has no restaurant to scope requests to and can't use the app.
    """

    def validate(self, attrs):
        data = super().validate(attrs)
        if not hasattr(self.user, 'profile'):
            from rest_framework_simplejwt.exceptions import AuthenticationFailed
            raise AuthenticationFailed('This account has no POS profile.')
        return data
