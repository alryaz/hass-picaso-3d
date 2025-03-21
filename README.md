# PICASO 3D Integration for Home Assistant

> Use PICASO 3D local UDP API to obtain information about printer(s).
>
> [![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)  
> [![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)  
> [![Supported](https://img.shields.io/badge/Supported%3F-Yes-green.svg?style=for-the-badge)](https://github.com/alryaz/hass-picaso-3d/graphs/commit-activity)  

> 💵 **Support the project development**  
> [![Donate via YooMoney](https://img.shields.io/badge/YooMoney-8B3FFD.svg?style=for-the-badge)](https://yoomoney.ru/to/410012369233217)  
> [![Donate via Tinkoff](https://img.shields.io/badge/Tinkoff-F8D81C.svg?style=for-the-badge)](https://www.tinkoff.ru/cf/3g8f1RTkf5G)  
> [![Donate via Sberbank](https://img.shields.io/badge/Sberbank-green.svg?style=for-the-badge)](https://www.sberbank.com/ru/person/dl/jc?linkname=3pDgknI7FY3z7tJnN)  
> [![Donate via DonationAlerts](https://img.shields.io/badge/DonationAlerts-fbaf2b.svg?style=for-the-badge)](https://www.donationalerts.com/r/alryaz)  

> 💬 **Technical Support**  
> [![Telegram Group](https://img.shields.io/endpoint?url=https%3A%2F%2Ftg.sumanjay.workers.dev%2Falryaz_ha_addons&style=for-the-badge)](https://telegram.dog/alryaz_ha_addons)

> ⚠️ **Warning!** This is not an official integration by PICASO 3D.

## Installation

### Home Assistant Community Store (HACS)

> 🎉  **Recommended installation method.**

[![Open your Home Assistant and access the repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=alryaz&repository=picaso-3d&category=integration)

1. Install HACS ([installation guide on the official website](https://hacs.xyz/docs/installation/installation/)).
2. Add the repository to the list of custom repositories:
    1. Open the main page of _HACS_.
    2. Navigate to the _Integrations_ section.
    3. Click the three dots in the top-right corner (additional menu).
    4. Select _Custom Repositories_.
    5. Copy `https://github.com/alryaz/hass-picaso-3d` into the input field.
    6. Choose _Integration_ from the dropdown menu.
    7. Click _Add_.
3. Search for `PICASO 3D` in the integrations search _(there may be multiple results!)_.
4. Install the latest version of the component by clicking the `Install` button.
5. Restart the _Home Assistant_ server.

### Manual Installation

> ⚠️ **Warning!** This method is **<ins>not recommended</ins>** due to the difficulty in maintaining the integration up-to-date.

1. Download the [archive with the latest stable version of the integration](https://github.com/alryaz/hass-picaso-3d/releases/latest/download/picaso_3d.zip).
2. Create a folder (if it doesn't already exist) named `custom_components` inside your Home Assistant configuration directory.
3. Create a folder named `picaso_3d` inside the `custom_components` folder.
4. Extract the contents of the downloaded archive into the `picaso_3d` folder.
5. Restart the _Home Assistant_ server.