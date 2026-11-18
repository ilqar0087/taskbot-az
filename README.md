# Task Worker AZ — Qazanc İzləyicisi

Telegram botu Gold Diggers, Arctic Rush, Lumberjack və Task Worker AZ tapşırıqlarından istifadəçinin əl ilə təsdiqlədiyi qazancı, reklam sayını və çıxarış tarixçəsini qeyd edir.

## Tətbiqlər və gündəlik plan
- Gold Diggers — 25 reklam hədəfi
- Arctic Rush — 25 reklam hədəfi
- Lumberjack — 24 reklam hədəfi
- Cəmi plan: 74 reklam/gün. Bu sərt limit deyil; faktiki say tətbiqin icazə verdiyi həddə görə dəyişir.
- Task Worker AZ tapşırıqları ayrıca qazanc mənbəyidir.

## Telegram komandaları
- `/start`, `/help` — kömək
- `/apps` — tətbiqlər və hədəflər
- `/email add email@gmail.com` — e-poçt profilini əlavə et
- `/email list` — profilləri göstər
- `/appstatus set 1 gold active` — profil 1 üçün Gold Diggers qeydiyyat statusunu aktiv kimi qeyd et
- `/appstatus list 1` — profil 1-in üç tətbiq üzrə statuslarını göstər
- `/record gold 1 120 20 qeyd` — profil 1 üçün 120 satoshi və 20 reklam qeydi
- `/record task - 500 0 tapşırıq` — Task Worker AZ qazanc qeydi
- `/balance` — qeyd edilmiş qazanc və çıxarış cəmi
- `/today` — bugünkü qeydlər
- `/wallet set BTC_ADDRESS` — Bitcoin on-chain qəbul ünvanı
- `/wallet` — Bitcoin ünvanını göstər
- `/lightning set name@walletofsatoshi.com` — Wallet of Satoshi Lightning ünvanını saxla
- `/lightning` — Lightning ünvanını göstər
- `/withdraw SATOSHI TXID` — artıq edilmiş çıxarışı qeyd et
- `/history` — tarixçə

## Railway dəyişənləri
- `BOT_TOKEN` və ya `TELEGRAM_BOT_TOKEN`
- `OWNER_TELEGRAM_ID` — yalnız sahibin Telegram ID-si
- `DATABASE_PATH=/data/taskbot.sqlite3` — persistent volume

## Təhlükəsizlik və məhdudiyyətlər
- Bot reklam açmır, videoya baxmır, klik etmir, hesablar arasında avtomatik giriş etmir və CAPTCHA keçmir.
- Çoxsaylı hesablar yalnız tətbiqin qaydaları buna açıq icazə verirsə istifadə edilməlidir.
- E-poçt ünvanları yalnız profil etiketi kimi saxlanılır. Gmail parolu, OTP, seed phrase və private key istənilmir və saxlanılmır.
- Tətbiq statusları yalnız istifadəçinin əl ilə daxil etdiyi uçot qeydləridir; hesab yaratma və tətbiqə giriş avtomatlaşdırılmır.
- Bot BTC köçürməsi etmir. Bitcoin on-chain və Lightning ünvanlarını ayrı saxlayır; istifadəçinin artıq etdiyi çıxarışı TXID ilə qeyd edir.
- Balans yalnız istifadəçinin daxil etdiyi qeydlərin cəmidir; real tətbiq və blokçeyn balansı deyil.
- Mövcud SQLite faylı və köhnə cədvəllər silinmir; yeni izləyici cədvəlləri ayrıca yaradılır.
