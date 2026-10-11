import * as cdk from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { AgentCoreStack } from '../lib/cdk-stack';
import { ConfigIO } from '@aws/agentcore-cdk';
import * as fs from 'fs';
import * as path from 'path';

test('AgentCoreStack synthesizes with empty spec', () => {
  const app = new cdk.App();
  const stack = new AgentCoreStack(app, 'TestStack', {
    spec: {
      name: 'testproject',
      version: 1,
      managedBy: 'CDK' as const,
      runtimes: [],
      memories: [],
      credentials: [],
      evaluators: [],
      onlineEvalConfigs: [],
      configBundles: [],
      policyEngines: [],
      payments: [],
      agentCoreGateways: [],
      mcpRuntimeTools: [],
      unassignedTargets: [],
      datasets: [],
      knowledgeBases: [],
    },
  });
  const template = Template.fromStack(stack);
  template.hasOutput('StackNameOutput', {
    Description: 'Name of the CloudFormation Stack',
  });
});

test('migrated gateway preserves deployed identities and references existing dependencies', async () => {
  const configRoot = path.resolve(__dirname, '../..');
  const config = new ConfigIO({ baseDir: configRoot });
  const spec = await config.readProjectSpec();
  const raw = JSON.parse(fs.readFileSync(path.join(configRoot, 'agentcore.json'), 'utf8'));
  const inventory = JSON.parse(fs.readFileSync(path.join(configRoot, '../existing-resources.json'), 'utf8'));
  const app = new cdk.App();
  const stack = new AgentCoreStack(app, inventory.stackName, {
    spec,
    mcpSpec: { agentCoreGateways: raw.agentCoreGateways },
    env: { account: inventory.account, region: inventory.region },
  });
  const resources = Template.fromStack(stack).toJSON().Resources;
  const recorded = inventory.cloudFormationResources
    .filter((r: { type: string }) => r.type !== 'AWS::CDK::Metadata')
    .map((r: { logicalId: string }) => r.logicalId).sort();
  const actual = Object.keys(resources)
    .filter(id => resources[id].Type !== 'AWS::CDK::Metadata').sort();
  expect(actual).toEqual(recorded);
  const targets = Object.values(resources).filter(
    (r: any) => r.Type === 'AWS::BedrockAgentCore::GatewayTarget'
  ) as any[];
  expect(targets.map(r => r.Properties.Name).sort())
    .toEqual(inventory.targets.map((t: { name: string }) => t.name).sort());
  for (const target of targets) {
    const expected = inventory.targets.find((t: { name: string }) => t.name === target.Properties.Name);
    expect(target.Properties.TargetConfiguration.Mcp.Lambda.LambdaArn).toBe(expected.lambdaArn);
  }
  expect(Object.values(resources).some((r: any) =>
    ['AWS::Lambda::Function', 'AWS::Bedrock::KnowledgeBase', 'AWS::S3::Bucket'].includes(r.Type)
  )).toBe(false);
});

