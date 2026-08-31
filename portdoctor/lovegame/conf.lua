function love.conf(t)
    local windowed = os.getenv("PORTDOCTOR_WINDOWED") == "1"

    t.identity = "portdoctor-r36s"
    t.version = "11.5"
    t.console = true

    t.window.title = "Port Doctor R36S"
    t.window.width = 640
    t.window.height = 480
    t.window.fullscreen = not windowed
    t.window.fullscreentype = "desktop"
    t.window.resizable = false
    t.window.vsync = 1
    t.window.highdpi = false

    t.modules.physics = false
    t.modules.video = false
    t.modules.audio = false -- This utility has no sounds and must not claim ALSA.
end
