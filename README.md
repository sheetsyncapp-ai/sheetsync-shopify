# SheetSync for Shopify 🚀

Micro-SaaS B2B para sincronizar pedidos de Shopify en tiempo real con Google Sheets. Diseñada para generar ingresos mensuales recurrentes ($9.99 a $19.99 USD/mes) con ultra-bajo churn.

---

## 🛠️ Cómo ejecutar el proyecto localmente

### 1. Instalar dependencias
Abre una terminal en esta carpeta y ejecuta:
```bash
python -m pip install -r requirements.txt
```

### 2. Iniciar el servidor
```bash
python -m uvicorn app.main:app --reload --port 8000
```

### 3. Abrir la interfaz
Entra en tu navegador a:
👉 [http://localhost:8000](http://localhost:8000)

Verás la interfaz con el diseño oficial de Shopify Polaris. Podrás:
* Conectar tu cuenta de Google.
* Configurar el ID de tu Google Sheet.
* Probar el botón **"Send Test Order"** para simular un pedido en tiempo real.

---

## 🔑 Cuentas necesarias para publicar en la Shopify App Store (Ambas son 100% gratuitas)

1. **Shopify Partners Account:**
   * Regístrate gratis en [partners.shopify.com](https://partners.shopify.com).
   * Te permite crear una tienda de desarrollo ilimitada y publicar tu app en la App Store de Shopify.
2. **Google Cloud Console:**
   * Entra a [console.cloud.google.com](https://console.cloud.google.com).
   * Crea un proyecto, activa la **Google Sheets API** y la **Google Drive API**, y obtén tu `Client ID` y `Client Secret` en la sección de *Credenciales OAuth 2.0*.
