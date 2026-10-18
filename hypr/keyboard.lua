-- AK680 MAX: раскладки и переключение EN/RU.
--
-- ВАЖНО: это ФРАГМЕНТ для твоего ~/.config/hypr/hyprland.lua, а не самостоятельный
-- конфиг. Полный личный hyprland.lua здесь не лежит специально (он в отдельном
-- приватном репозитории). Если у тебя уже есть свой `hl.config({ input = ... })` —
-- влей туда поля `kb_*`/`numlock_by_default`, а не дублируй вызов.

-- 1. Раскладки: us + ru (переключаются биндами ниже)
hl.config({
	input = {
		kb_layout = "us,ru",
		kb_variant = "",
		kb_model = "",
		kb_options = "",
		kb_rules = "",
		numlock_by_default = true,
	},
})

-- 2. Правый кластер: RAlt = EN, RCtrl = RU.
--    Скрипт: bin/layout-switch.sh → ~/bin/layout-switch.sh (обходит все клавиатуры
--    Hyprland; почему с `--` — см. README, «Почему скрипт переключения такой странный»).
hl.bind("code:108", hl.dsp.exec_cmd("~/bin/layout-switch.sh 0"))
hl.bind("code:105", hl.dsp.exec_cmd("~/bin/layout-switch.sh 1"))

-- 3. Deskflow (если используется этот software-KVM): серверная часть нужна, чтобы
--    клавиатура/мышь шарились на клиент, а подсветка клавиатуры перекрашивалась по
--    активному экрану (systemd user service deskflow-color.service, см. README).
hl.on("hyprland.start", function()
	hl.exec_cmd("deskflow-core server")
end)
