// Azure App Service with Microsoft Entra ID Authentication (Easy Auth)
// Pure PaaS deployment on Linux Free (F1) / Basic (B1) Tier

param location string = resourceGroup().location
param appName string = 'rulebound-api-${uniqueString(resourceGroup().id)}'
param entraClientId string
param entraTenantId string

// 1. App Service Plan (Linux Free Tier F1 or Basic B1)
resource appServicePlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: 'asp-${appName}'
  location: location
  kind: 'linux'
  sku: {
    name: 'B1'
    tier: 'Basic'
    size: 'B1'
    family: 'B'
    capacity: 1
  }
  properties: {
    reserved: true
  }
}

// 2. Web App Service (Python 3.11 Runtime)
resource webApp 'Microsoft.Web/sites@2022-09-01' = {
  name: appName
  location: location
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appCommandLine: 'python deploy/azure/app.py'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
    }
  }
}

// 3. Built-In Authentication / Easy Auth with Microsoft Entra ID (v2 Auth Config)
resource authConfig 'Microsoft.Web/sites/config@2022-09-01' = {
  parent: webApp
  name: 'authsettingsV2'
  properties: {
    platform: {
      enabled: true
      runtimeVersion: '~1'
    }
    globalValidation: {
      requireAuthentication: true
      unauthenticatedClientAction: 'Return401'
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: entraClientId
          openIdIssuer: 'https://login.microsoftonline.com/${entraTenantId}/v2.0'
        }
        validation: {
          allowedAudiences: [
            'api://${appName}'
            entraClientId
          ]
        }
      }
    }
  }
}

output endpointUrl string = 'https://${webApp.properties.defaultHostName}'
output appServicePlanId string = appServicePlan.id
