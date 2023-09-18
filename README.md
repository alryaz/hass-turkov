# _Turkov_ для Home Assistant
> Облачное и локальное управление вентиляционными устройствами фирмы Turkov.
>
> [![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
> [![Лицензия](https://img.shields.io/badge/%D0%9B%D0%B8%D1%86%D0%B5%D0%BD%D0%B7%D0%B8%D1%8F-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
> [![Поддержка](https://img.shields.io/badge/%D0%9F%D0%BE%D0%B4%D0%B4%D0%B5%D1%80%D0%B6%D0%B8%D0%B2%D0%B0%D0%B5%D1%82%D1%81%D1%8F%3F-%D0%B4%D0%B0-green.svg?style=for-the-badge)](https://github.com/alryaz/hass-pandora-cas/graphs/commit-activity)

> 💵 **Пожертвование на развитие проекта**  
> [![Пожертвование YooMoney](https://img.shields.io/badge/YooMoney-8B3FFD.svg?style=for-the-badge)](https://yoomoney.ru/to/410012369233217)
> [![Пожертвование Тинькофф](https://img.shields.io/badge/Tinkoff-F8D81C.svg?style=for-the-badge)](https://www.tinkoff.ru/cf/3g8f1RTkf5G)
> [![Пожертвование PayPal](https://img.shields.io/badge/PayPal-159BD7.svg?style=for-the-badge)](https://www.paypal.me/alryaz)
> [![Пожертвование Cбербанк](https://img.shields.io/badge/Сбербанк-green.svg?style=for-the-badge)](https://www.sberbank.com/ru/person/dl/jc?linkname=3pDgknI7FY3z7tJnN)
>
> 💬 **Техническая поддержка**  
> [![Группа в Telegram](https://img.shields.io/endpoint?url=https%3A%2F%2Ftg.sumanjay.workers.dev%2Falryaz_ha_addons&style=for-the-badge)](https://telegram.dog/alryaz_ha_addons)

> 📚 **Документация API Turkov**  
> [![Документация API Turkov](https://img.shields.io/badge/Turkov-Wiki-111111.svg?style=for-the-badge)](https://wiki.turkov.ru/ru/equipment/wifi/pool)

## Установка
### Посредством HACS

[![Открыть Ваш Home Assistant и открыть репозиторий внутри Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=alryaz&repository=hass-turkov&category=integration)

1. Откройте HACS (через `Extensions` в боковой панели)
1. Добавьте новый произвольный репозиторий:
   1. Выберите `Integration` (`Интеграция`) в качестве типа репозитория
   1. Введите ссылку на репозиторий: `https://github.com/alryaz/hass-turkov`
   1. Нажмите кнопку `Add` (`Добавить`)
   1. Дождитесь добавления репозитория (занимает до 10 секунд)
   1. Теперь вы должны видеть доступную интеграцию `Turkov` в списке новых интеграций.
1. Нажмите кнопку `Install` чтобы увидеть доступные версии
1. Установите последнюю версию нажатием кнопки `Install`
1. Перезапустите Home Assistant

## Настройка

[![Открыть Ваш Home Assistant и начать настройку интеграции.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=turkov)

Нажмите на кнопку выше, или следуйте следующим инструкциям:
1. Откройте `Настройки` -> `Интеграции`
1. Нажмите внизу справа страницы кнопку с плюсом
1. Введите в поле поиска `Turkov`  
   - Если интеграция не была найдена на данном этапе, перезапустите Home Assistant и очистите кеш браузера.
1. Выберите первый результат из списка
2. Следуйте инструкциям, описываемым на экране.
1. После завершения настройки начнётся обновление состояний объектов.

## Взаимодействие

Компонент создаёт два типа объектов:
- `climate.<имя устройства>`
- `sensor.<имя устройства>_<тип сенсора>` - сенсоры для значений, не используемых в объекте climate.
