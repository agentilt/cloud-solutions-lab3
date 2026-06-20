"""Bedrock Knowledge Base over S3 Vectors — RAG grounding for the architecture agents.

Builds a real retrieval pipeline:
  guidance corpus (S3)  ->  Bedrock Knowledge Base  ->  S3 Vectors index
The agent's query_reference_guidance tool calls bedrock-agent-runtime:Retrieve
against this KB. No L2 construct exists yet for KB-on-S3-Vectors, so this uses the
L1 CfnKnowledgeBase / CfnVectorBucket / CfnIndex resources.

Note: ingestion (populating the index from the corpus) is a Bedrock ingestion job,
triggered post-deploy (or on corpus change). Until the first ingestion runs,
Retrieve returns no matches and the tool falls back to its curated guidance.
"""
from pathlib import Path

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3_deployment
from aws_cdk import aws_s3vectors as s3vectors
from constructs import Construct

CORPUS_DIR = Path(__file__).resolve().parent.parent / "knowledge_corpus"
EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSION = 1024  # Titan Text Embeddings V2 default


class KnowledgeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. Private corpus bucket, seeded with the guidance documents.
        corpus_bucket = s3.Bucket(
            self,
            "CorpusBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        s3_deployment.BucketDeployment(
            self,
            "CorpusDeployment",
            sources=[s3_deployment.Source.asset(str(CORPUS_DIR))],
            destination_bucket=corpus_bucket,
            destination_key_prefix="guidance/",
            retain_on_delete=False,
        )

        # 2. S3 Vectors store: vector bucket + index sized to the embedding model.
        vector_bucket = s3vectors.CfnVectorBucket(self, "VectorBucket")
        index = s3vectors.CfnIndex(
            self,
            "VectorIndex",
            index_name="cloudcompass-guidance",
            data_type="float32",
            dimension=EMBEDDING_DIMENSION,
            distance_metric="cosine",
            vector_bucket_arn=vector_bucket.attr_vector_bucket_arn,
        )
        index.add_dependency(vector_bucket)

        embedding_model_arn = (
            f"arn:{self.partition}:bedrock:{self.region}::foundation-model/{EMBEDDING_MODEL}"
        )

        # 3. Knowledge Base service role: embed (InvokeModel), read corpus, write vectors.
        kb_role = iam.Role(
            self,
            "KnowledgeBaseRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Bedrock Knowledge Base ingestion/retrieval role for CloudCompass.",
        )
        kb_role.add_to_policy(
            iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=[embedding_model_arn])
        )
        corpus_bucket.grant_read(kb_role)
        kb_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3vectors:PutVectors",
                    "s3vectors:GetVectors",
                    "s3vectors:QueryVectors",
                    "s3vectors:ListVectors",
                    "s3vectors:DeleteVectors",
                    "s3vectors:GetIndex",
                ],
                resources=[vector_bucket.attr_vector_bucket_arn, index.attr_index_arn],
            )
        )

        # 4. The Knowledge Base (VECTOR type, S3_VECTORS storage).
        self.knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "KnowledgeBase",
            name=f"cloudcompass-guidance-{self.node.addr[:8]}",
            role_arn=kb_role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=(
                    bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                        embedding_model_arn=embedding_model_arn,
                    )
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="S3_VECTORS",
                s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                    vector_bucket_arn=vector_bucket.attr_vector_bucket_arn,
                    index_arn=index.attr_index_arn,
                ),
            ),
        )
        self.knowledge_base.add_dependency(index)
        self.knowledge_base.node.add_dependency(kb_role)

        # 5. S3 data source pointing at the seeded corpus prefix.
        data_source = bedrock.CfnDataSource(
            self,
            "GuidanceDataSource",
            name="cloudcompass-guidance-corpus",
            knowledge_base_id=self.knowledge_base.attr_knowledge_base_id,
            data_deletion_policy="RETAIN",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=corpus_bucket.bucket_arn,
                    inclusion_prefixes=["guidance/"],
                ),
            ),
        )
        data_source.node.add_dependency(corpus_bucket)

        self.knowledge_base_id = self.knowledge_base.attr_knowledge_base_id
        self.knowledge_base_arn = self.knowledge_base.attr_knowledge_base_arn

        CfnOutput(self, "KnowledgeBaseId", value=self.knowledge_base_id)
        CfnOutput(self, "KnowledgeBaseArn", value=self.knowledge_base_arn)
        CfnOutput(self, "DataSourceId", value=data_source.attr_data_source_id)
