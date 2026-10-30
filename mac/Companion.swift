import AppKit
import WebKit
import AVFoundation
import CoreGraphics

// Borderless panels still need keyboard focus for setup and accessibility.
final class CompanionPanel: NSPanel {
    override var canBecomeKey: Bool { true }
}
final class PixelGrip: NSView {
    var pointerStart: NSPoint?
    var windowStart: NSPoint?
    override var mouseDownCanMoveWindow: Bool { false }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func resetCursorRects() { addCursorRect(bounds, cursor: .openHand) }
    override func mouseDown(with event: NSEvent) {
        pointerStart = NSEvent.mouseLocation
        windowStart = window?.frame.origin
        NSCursor.closedHand.push()
    }
    override func mouseDragged(with event: NSEvent) {
        guard let pointer = pointerStart, let origin = windowStart else { return }
        let current = NSEvent.mouseLocation
        window?.setFrameOrigin(NSPoint(x: origin.x + current.x - pointer.x, y: origin.y + current.y - pointer.y))
    }
    override func mouseUp(with event: NSEvent) {
        if let origin = windowStart, let end = window?.frame.origin {
            NSLog("Companion drag completed: %.0f, %.0f", end.x - origin.x, end.y - origin.y)
        }
        if pointerStart != nil { NSCursor.pop() }
        pointerStart = nil; windowStart = nil
    }
    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedRed: 0.08, green: 0.14, blue: 0.18, alpha: 0.9).setFill()
        bounds.fill()
        NSColor(calibratedRed: 0.4, green: 0.55, blue: 0.52, alpha: 1).setStroke()
        let edge = NSBezierPath(rect: bounds.insetBy(dx: 0.5, dy: 0.5))
        edge.lineWidth = 1; edge.stroke()
        NSColor(calibratedRed: 0.93, green: 0.95, blue: 0.86, alpha: 1).setFill()
        for x in [4.0, 10.0, 16.0] {
            for y in [10.0, 18.0] { NSRect(x: x, y: y, width: 3, height: 3).fill() }
        }
    }
}

// A real floating macOS panel; the web view only holds a limited surface identity.
final class CompanionApp: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, NSWindowDelegate, WKScriptMessageHandler {
    var panel: NSPanel!
    var web: WKWebView!
    var grip: PixelGrip!
    var activity: NSObjectProtocol?
    var wakeObserver: NSObjectProtocol?
    var displayObservers: [NSObjectProtocol] = []
    var displayTimer: Timer?
    var retry: DispatchWorkItem?
    let address = URL(string: ProcessInfo.processInfo.environment["OKABEBOT_SURFACE_URL"] ?? "http://localhost:8768/companion/?native=1")!
    func applicationDidFinishLaunching(_ notification: Notification) {
        activity = ProcessInfo.processInfo.beginActivity(options: [.userInitiatedAllowingIdleSystemSleep], reason: "Companion surface presence and animation")
        let configuration = WKWebViewConfiguration()
        configuration.mediaTypesRequiringUserActionForPlayback = []
        configuration.userContentController.add(self, name: "companion")
        web = WKWebView(frame: NSRect(x: 0, y: 0, width: 240, height: 296), configuration: configuration)
        web.autoresizingMask = [.width, .height]
        web.navigationDelegate = self
        web.uiDelegate = self
        panel = CompanionPanel(contentRect: NSRect(x: 100, y: 100, width: 240, height: 296), styleMask: [.borderless, .resizable], backing: .buffered, defer: false)
        panel.title = "Little Lab"
        panel.delegate = self
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        panel.isMovable = true
        panel.minSize = NSSize(width: 220, height: 270)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        web.setValue(false, forKey: "drawsBackground")
        if #available(macOS 12.0, *) { web.underPageBackgroundColor = .clear }
        let container = NSView(frame: NSRect(x: 0, y: 0, width: 240, height: 310))
        web.frame = NSRect(x: 0, y: 0, width: 240, height: 296)
        container.addSubview(web)
        grip = PixelGrip(frame: NSRect(x: 18, y: 8, width: 24, height: 32))
        grip.autoresizingMask = [.maxXMargin, .maxYMargin]
        grip.setAccessibilityElement(true)
        grip.setAccessibilityRole(.group)
        grip.setAccessibilityLabel("Drag companion window")
        container.addSubview(grip)
        panel.contentView = container
        panel.setContentSize(NSSize(width: 240, height: 310))
        panel.makeKeyAndOrderFront(nil)
        loadPage()
        wakeObserver = NSWorkspace.shared.notificationCenter.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { [weak self] _ in
            guard let self = self else { return }
            self.web.evaluateJavaScript("window.dispatchEvent(new Event('companion-wake'))", completionHandler: nil)
        }
        for (notification, cause) in [(NSWorkspace.screensDidWakeNotification, "wake"), (NSWorkspace.screensDidSleepNotification, "sleep")] {
            displayObservers.append(NSWorkspace.shared.notificationCenter.addObserver(forName: notification, object: nil, queue: .main) { [weak self] _ in
                self?.publishDisplay(cause)
            })
        }
        displayTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in self?.publishDisplay("snapshot") }
        NSApplication.shared.activate(ignoringOtherApps: true)
    }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        let origin = message.frameInfo.securityOrigin
        guard message.frameInfo.isMainFrame, origin.host == address.host,
              origin.protocol == address.scheme, origin.port == (address.port ?? (address.scheme == "https" ? 443 : 80)),
              let action = message.body as? String else { return }
        if action == "permissions" { publishMicrophonePermission(); return }
        if action == "close" { panel.close(); return }
        guard action == "expanded" || action == "compact" else { return }
        let size = action == "expanded" ? NSSize(width: 320, height: 480) : NSSize(width: 240, height: 310)
        panel.setContentSize(size)
        grip.isHidden = action == "expanded"
        grip.frame = NSRect(x: (size.width - 204) / 2, y: 8, width: 24, height: 32)
        if let screen = panel.screen {
            let bounds = screen.visibleFrame
            panel.setFrameOrigin(NSPoint(x: max(bounds.minX, min(panel.frame.minX, bounds.maxX - panel.frame.width)), y: max(bounds.minY, min(panel.frame.minY, bounds.maxY - panel.frame.height))))
        }
    }
    func windowDidResize(_ notification: Notification) {
        guard let grip = grip, let content = panel.contentView else { return }
        grip.frame = NSRect(x: (content.bounds.width - 204) / 2, y: 8, width: 24, height: 32)
    }
    func publishMicrophonePermission() {
        guard let url = web.url, url.scheme == address.scheme, url.host == address.host,
              url.port == address.port else { return }
        let state: String
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: state = "granted"
        case .notDetermined: state = "prompt"
        default: state = "denied"
        }
        // Enum-only projection to our trusted page; no capture or permission request.
        web.evaluateJavaScript("window.dispatchEvent(new CustomEvent('companion-permissions', {detail: {microphone: '\(state)'}}))", completionHandler: nil)
    }
    func publishDisplay(_ cause: String) {
        guard let url = web.url, url.scheme == address.scheme, url.host == address.host, url.port == address.port else { return }
        let state = cause == "sleep" ? "off" : cause == "wake" ? "on" : (CGDisplayIsAsleep(CGMainDisplayID()) != 0 ? "off" : "on")
        let value: [String: Any] = ["state": state, "cause": cause, "observed_at": Date().timeIntervalSince1970, "event_id": UUID().uuidString]
        guard let data = try? JSONSerialization.data(withJSONObject: value), let json = String(data: data, encoding: .utf8) else { return }
        web.evaluateJavaScript("window.dispatchEvent(new CustomEvent('companion-display', {detail: \(json)}))", completionHandler: nil)
    }
    func loadPage() {
        web.load(URLRequest(url: address, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 8))
    }
    func reconnect() {
        NSLog("Companion navigation reconnect")
        retry?.cancel()
        panel.title = "Little Lab · reconnecting"
        let work = DispatchWorkItem { [weak self] in self?.loadPage() }
        retry = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 2, execute: work)
    }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { reconnect() }
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { reconnect() }
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) { reconnect() }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { retry?.cancel(); panel.title = "Little Lab"; NSLog("Companion page ready") }
    func applicationWillTerminate(_ notification: Notification) { if let wakeObserver = wakeObserver { NSWorkspace.shared.notificationCenter.removeObserver(wakeObserver) }; displayTimer?.invalidate(); for observer in displayObservers { NSWorkspace.shared.notificationCenter.removeObserver(observer) }; if let activity = activity { ProcessInfo.processInfo.endActivity(activity) } }
    // Permission dialogs are ordinary windows; the floating NSPanel is not.
    // AppKit's last-window rule would quit when a mic consent dialog closes.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func windowWillClose(_ notification: Notification) {
        if let window = notification.object as? NSWindow, window === panel { NSApplication.shared.terminate(nil) }
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        decisionHandler(url.scheme == address.scheme && url.host == address.host && url.port == address.port ? .allow : .cancel)
    }
    @available(macOS 12.0, *)
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin, initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        guard frame.isMainFrame, origin.host == address.host, origin.protocol == address.scheme,
              origin.port == (address.port ?? (address.scheme == "https" ? 443 : 80)), type == .microphone else { decisionHandler(.deny); return }
        // Reuse this app's OS consent for its one trusted origin; do not present
        // WebKit's additional transient permission sheet on every launch.
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: publishMicrophonePermission(); decisionHandler(.grant)
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .audio) { allowed in
                DispatchQueue.main.async { self.publishMicrophonePermission(); decisionHandler(allowed ? .grant : .deny) }
            }
        default: decisionHandler(.deny)
        }
    }
}
let app = NSApplication.shared
let delegate = CompanionApp()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
