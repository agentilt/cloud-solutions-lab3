"""Cognito authentication for CloudCompass Builder."""
from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_cognito as cognito
from constructs import Construct


class AuthStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        frontend_url: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.user_pool = cognito.UserPool(
            self,
            "UserPool",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=10,
                require_digits=True,
                require_lowercase=True,
                require_uppercase=True,
                require_symbols=False,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.user_pool_client = cognito.UserPoolClient(
            self,
            "UserPoolClient",
            user_pool=self.user_pool,
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PROFILE,
                ],
                callback_urls=[frontend_url, "http://localhost:8080/", "http://localhost:3000/"],
                logout_urls=[frontend_url, "http://localhost:8080/", "http://localhost:3000/"],
            ),
        )

        domain_prefix = f"cloudcompass-{self.node.addr[:8].lower()}"
        self.user_pool_domain = self.user_pool.add_domain(
            "HostedUiDomain",
            cognito_domain=cognito.CognitoDomainOptions(domain_prefix=domain_prefix),
        )

        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=self.user_pool_client.user_pool_client_id)
        CfnOutput(
            self,
            "HostedUiDomain",
            value=self.user_pool_domain.base_url(),
        )
