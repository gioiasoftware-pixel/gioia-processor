# 🔧 Fix Deploy Multipli Railway

## Problema
Quando fai commit, partono **3 deploy simultanei** invece di 1.

## 🔍 Possibili Cause

### 1. Multiple Servizi Railway Collegati allo Stesso Repository
Railway potrebbe avere **3 servizi** diversi collegati allo stesso repository GitHub.

**Verifica:**
1. Vai su Railway.app → Dashboard
2. Controlla se ci sono **3 servizi** diversi nel progetto
3. Ogni servizio potrebbe essere collegato allo stesso repository

**Soluzione:**
- Mantieni solo **1 servizio** per il processor
- Rimuovi o disabilita gli altri 2 servizi duplicati

### 2. Multiple Branch che Triggerano Deploy
Railway potrebbe essere configurato per fare deploy da **3 branch diversi**.

**Verifica:**
1. Railway → Servizio → Settings → Source
2. Controlla se ci sono **multiple branch** configurati
3. Verifica se ci sono **3 branch** che triggerano deploy (es. main, develop, staging)

**Soluzione:**
- Configura solo **1 branch** per deploy (es. `main`)
- Disabilita deploy automatici dagli altri branch

### 3. Webhook GitHub Multipli
Potrebbero esserci **3 webhook GitHub** che triggerano deploy.

**Verifica:**
1. GitHub → Repository → Settings → Webhooks
2. Controlla se ci sono **multiple webhook** per Railway
3. Ogni webhook potrebbe triggerare un deploy

**Soluzione:**
- Mantieni solo **1 webhook** per Railway
- Rimuovi i webhook duplicati

### 4. Railway Auto-Deploy Multipli
Railway potrebbe avere **auto-deploy** abilitato su più servizi.

**Verifica:**
1. Railway → Ogni servizio → Settings → Source
2. Controlla se **"Auto Deploy"** è abilitato su più servizi

**Soluzione:**
- Disabilita auto-deploy sui servizi duplicati
- Mantieni solo su **1 servizio principale**

## ✅ Soluzione Rapida

### Step 1: Identifica i 3 Deploy
1. Vai su Railway.app → Dashboard
2. Vai su **Deployments** tab
3. Controlla quali **3 servizi** stanno facendo deploy
4. Annota i nomi dei servizi

### Step 2: Mantieni Solo 1 Servizio
1. Per ogni servizio duplicato:
   - Vai su Settings → Source
   - Clicca **"Disconnect"** o **"Disable Auto Deploy"**
2. Mantieni solo **1 servizio attivo** con auto-deploy

### Step 3: Verifica
1. Fai un commit di test
2. Dovrebbe partire solo **1 deploy**
3. Se ancora partono 3, controlla webhook GitHub

## 🎯 Configurazione Consigliata

**1 Servizio Railway:**
- Nome: `gioia-processor-production`
- Repository: `gioiasoftware-pixel/gioia-processor`
- Branch: `main`
- Auto Deploy: ✅ Abilitato
- Builder: `NIXPACKS`

**Altri servizi:**
- Disabilita auto-deploy
- Oppure rimuovi completamente

## 📝 Verifica Finale

Dopo aver configurato:
1. Fai un commit di test
2. Verifica che parta solo **1 deploy**
3. Controlla che il deploy sia veloce (~3-5 minuti)

## ⚠️ Nota

Se hai bisogno di **3 ambienti** (es. dev, staging, production), è normale avere 3 servizi, ma dovrebbero essere configurati su **branch diversi** o **triggerati manualmente**, non tutti automaticamente su ogni commit.

