import {
  AbsoluteFill,
  Img,
  OffthreadVideo,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig
} from 'remotion';

const fallbackReco = [];

const asAsset = (value) => {
  if (!value || typeof value !== 'string') {
    return null;
  }
  return staticFile(value.replace(/^\/+/, ''));
};

const defaultText = {
  title: 'LoFi Jesus Prayer Mix ✨',
  channel: 'LoFi Jesus',
  subscribers: '124K subscribers',
  cta: 'Subscribe to LoFi Jesus',
  views: '1.2M views • live',
  meta: 'Live prayer stream',
  comments: ['Peace over your home tonight.', 'This keeps my prayer time focused.'],
  recommendedTitles: [
    'Night Prayer LoFi 🌙',
    'Scripture Sleep Mix 😴',
    'Morning Worship Beats ☀️',
    'Crosslight Focus ✝️'
  ],
  recommendedMeta: [
    'LoFi Jesus • 842K views • 8h',
    'LoFi Jesus • 1.3M views • 2d',
    'LoFi Jesus • 599K views • 1w',
    'LoFi Jesus • 411K views • 3w'
  ]
};

const defaultTheme = {
  background:
    'radial-gradient(1300px 780px at 8% -18%, #21375f 0%, transparent 65%), radial-gradient(1200px 700px at 106% -8%, #472729 0%, transparent 60%), #05070d',
  panelBackground:
    'linear-gradient(145deg, rgba(12,16,27,0.92), rgba(9,13,22,0.90)), radial-gradient(900px 500px at 5% -10%, rgba(69,104,176,0.20), transparent 66%)',
  panelBorder: '1px solid rgba(255,255,255,0.11)',
  accent: '#ff3d45',
  primaryText: '#eff4ff',
  mutedText: '#9ca8c3'
};

const loopProgress = (frame, periodFrames) => {
  const period = Math.max(1, periodFrames);
  const local = frame % period;
  return interpolate(local, [0, period], [0.04, 0.96], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
};

const normalizeTextLine = (value) => {
  if (typeof value !== 'string') {
    return '';
  }
  return value.replace(/\s*\n+\s*/g, ' • ').trim();
};

export const OverlayComposition = (props) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const p = props || {};
  const assets = p.assets || {};
  const words = {...defaultText, ...(p.text || {})};
  const theme = {...defaultTheme, ...(p.theme || {})};

  const mainVideo = asAsset(assets.mainVideo);
  const mainStill = asAsset(assets.mainStill);
  const ytLogo = asAsset(assets.ytLogo);
  const spotifyLogo = asAsset(assets.spotifyLogo);
  const reco = Array.isArray(assets.reco) && assets.reco.length ? assets.reco : fallbackReco;
  const recoWithFallback = reco.length
    ? reco
    : mainStill
      ? [assets.mainStill, assets.mainStill, assets.mainStill, assets.mainStill]
      : [null, null, null, null];
  const recommendedTitles = Array.isArray(words.recommendedTitles) && words.recommendedTitles.length
    ? words.recommendedTitles
    : defaultText.recommendedTitles;

  const baseScale = Math.min(width / 3840, height / 2160);
  const breathing = Math.sin((frame / Math.max(1, fps)) * (Math.PI * 2 / 10));
  const driftX = Math.sin((frame / Math.max(1, fps)) * (Math.PI * 2 / 14)) * 10 * baseScale;
  const driftY = Math.cos((frame / Math.max(1, fps)) * (Math.PI * 2 / 16)) * 7 * baseScale;

  const intro = spring({
    frame,
    fps,
    config: {
      damping: 220,
      stiffness: 130,
      mass: 0.95
    }
  });

  const shellScale = 0.985 + intro * 0.015 + breathing * 0.003;
  const progress = loopProgress(frame, Math.round(8 * fps));
  const subscribePulse = 1 + Math.sin((frame / Math.max(1, fps)) * (Math.PI * 2 / 3.4)) * 0.015;
  const sheenLoopFrames = Math.max(1, Math.round(5.4 * fps));
  const sheenLocalFrame = frame % sheenLoopFrames;
  const sheenX = interpolate(
    sheenLocalFrame,
    [0, Math.round(0.28 * sheenLoopFrames), Math.round(0.60 * sheenLoopFrames), sheenLoopFrames],
    [-1.3, 1.3, -1.3, -1.3],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp'
    }
  );
  const subscribeIn = spring({
    frame: frame - Math.round(0.25 * fps),
    fps,
    durationInFrames: Math.max(1, Math.round(0.9 * fps)),
    config: {
      damping: 24,
      stiffness: 140,
      mass: 0.95
    }
  });
  const subscribeLiftY = interpolate(subscribeIn, [0, 1], [24 * baseScale, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  const subscribeFloatY = Math.sin((frame / Math.max(1, fps)) * (Math.PI * 2 / 4.8)) * (3 * baseScale);
  const subscribeScale = interpolate(subscribeIn, [0, 1], [0.84, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  }) * subscribePulse;
  const glowBreath = 0.5 + 0.5 * Math.sin((frame / Math.max(1, fps)) * (Math.PI * 2 / 2.9));
  const ringLoopFrames = Math.max(1, Math.round(2.8 * fps));
  const ringProgress = (frame % ringLoopFrames) / ringLoopFrames;
  const ringScale = interpolate(ringProgress, [0, 1], [1, 1.22], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  const ringOpacity = interpolate(ringProgress, [0, 1], [0.30, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  const railLoopFrames = Math.max(1, Math.round(22 * fps));
  const railProgress = (frame % railLoopFrames) / railLoopFrames;
  const railTranslatePct = -50 * railProgress;
  const railGap = Math.round(10 * baseScale);

  const panelWidth = width - Math.round(120 * baseScale);
  const panelHeight = height - Math.round(120 * baseScale);
  const mainTitleScale = 1.52;
  const cardTitleScale = 1.65;

  return (
    <AbsoluteFill
      style={{
        background:
          theme.background,
        color: theme.primaryText,
        fontFamily: 'Inter, Avenir, Helvetica, sans-serif',
        justifyContent: 'center',
        alignItems: 'center'
      }}
    >
      <AbsoluteFill
        style={{
          pointerEvents: 'none',
          opacity: 0.48,
          background:
            'radial-gradient(800px 380px at 65% 4%, rgba(113,173,255,0.22), transparent 70%), radial-gradient(700px 340px at 20% 90%, rgba(250,134,113,0.12), transparent 72%)',
          transform: `translate(${Math.round(driftX * 0.4)}px, ${Math.round(driftY * 0.4)}px)`
        }}
      />

      <div
        style={{
          width: panelWidth,
          height: panelHeight,
          padding: Math.round(38 * baseScale),
          borderRadius: Math.round(42 * baseScale),
          border: theme.panelBorder,
          background: theme.panelBackground,
          boxShadow: '0 55px 130px rgba(0,0,0,0.58)',
          display: 'grid',
          gridTemplateColumns: '0.86fr 0.64fr',
          gap: Math.round(20 * baseScale),
          transform: `translate(${Math.round(driftX)}px, ${Math.round(driftY)}px) scale(${shellScale})`,
          overflow: 'hidden'
        }}
      >
        <div style={{display: 'grid', gridTemplateRows: '1fr auto', gap: Math.round(22 * baseScale), minWidth: 0}}>
          <div
            style={{
              borderRadius: Math.round(26 * baseScale),
              border: '1px solid rgba(255,255,255,0.12)',
              background: '#070b14',
              overflow: 'hidden',
              position: 'relative'
            }}
          >
            {mainVideo ? (
              <OffthreadVideo
                src={mainVideo}
                muted
                volume={0}
                loop
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'cover',
                  transform: `scale(${1.01 + breathing * 0.006})`
                }}
              />
            ) : mainStill ? (
              <Img src={mainStill} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
            ) : null}
            <div
              style={{
                position: 'absolute',
                left: Math.round(24 * baseScale),
                right: Math.round(24 * baseScale),
                bottom: Math.round(18 * baseScale),
                height: Math.round(8 * baseScale),
                borderRadius: 999,
                background: 'rgba(255,255,255,0.24)',
                overflow: 'hidden'
              }}
            >
              <div
                style={{
                  width: `${Math.round(progress * 100)}%`,
                  height: '100%',
                  background: `linear-gradient(90deg, #ff6c73 0%, ${theme.accent} 65%, #ff2b37 100%)`,
                  boxShadow: '0 0 22px rgba(255,72,78,0.55)'
                }}
              />
            </div>
          </div>

          <div
            style={{
              borderRadius: Math.round(26 * baseScale),
              border: '1px solid rgba(255,255,255,0.11)',
              background: 'linear-gradient(180deg, rgba(16,20,31,0.88), rgba(12,16,25,0.88))',
              padding: Math.round(26 * baseScale),
              display: 'grid',
              gap: Math.round(20 * baseScale)
            }}
          >
            <div style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: Math.round(22 * baseScale)}}>
              <div
                style={{
                  fontWeight: 800,
                  fontSize: Math.round(82 * baseScale * mainTitleScale),
                  lineHeight: 1.06,
                  letterSpacing: 0.2,
                  transform: `translateY(${Math.round((1 - intro) * 16)}px)`,
                  textWrap: 'balance',
                  minWidth: 0
                }}
              >
                {words.title}
              </div>
              <div style={{display: 'inline-flex', alignItems: 'center', gap: Math.round(12 * baseScale), flexShrink: 0}}>
                {ytLogo ? (
                  <div
                    style={{
                      width: Math.round(148 * 1.5 * baseScale),
                      height: Math.round(148 * 1.5 * baseScale),
                      borderRadius: 999,
                      overflow: 'hidden',
                      border: '1px solid rgba(255,255,255,0.22)',
                      background: 'rgba(255,255,255,0.08)',
                      display: 'grid',
                      placeItems: 'center',
                      boxShadow: '0 8px 20px rgba(0,0,0,0.25)'
                    }}
                  >
                    <Img src={ytLogo} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
                  </div>
                ) : null}
                {spotifyLogo ? (
                  <div
                    style={{
                      width: Math.round(148 * 1.5 * baseScale),
                      height: Math.round(148 * 1.5 * baseScale),
                      borderRadius: 999,
                      overflow: 'hidden',
                      border: '1px solid rgba(255,255,255,0.22)',
                      background: 'rgba(255,255,255,0.08)',
                      display: 'grid',
                      placeItems: 'center',
                      boxShadow: '0 8px 20px rgba(0,0,0,0.25)'
                    }}
                  >
                    <Img src={spotifyLogo} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
                  </div>
                ) : null}
              </div>
            </div>

            <div
              style={{
                position: 'relative',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                width: '100%',
                marginTop: Math.round(-4 * baseScale),
                marginBottom: Math.round(10 * baseScale),
                padding: `${Math.round(8 * baseScale)}px 0 ${Math.round(24 * baseScale)}px`,
                overflow: 'hidden'
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  width: '66%',
                  maxWidth: Math.round(920 * baseScale),
                  height: Math.round(210 * baseScale),
                  borderRadius: 999,
                  background:
                    'radial-gradient(60% 80% at 50% 50%, rgba(255,214,122,0.32), rgba(255,214,122,0) 78%)',
                  filter: `blur(${Math.round(10 * baseScale)}px)`,
                  opacity: 0.46 + glowBreath * 0.26,
                  transform: `translateY(${Math.round((subscribeLiftY - subscribeFloatY) * 0.55)}px) scale(${0.98 + glowBreath * 0.06})`,
                  pointerEvents: 'none'
                }}
              />
              <div
                style={{
                  position: 'relative',
                  isolation: 'isolate',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: `${Math.round(72 * baseScale)}px ${Math.round(154 * baseScale)}px`,
                  borderRadius: 999,
                  border: '1px solid rgba(255,250,228,0.68)',
                  background:
                    'linear-gradient(135deg, #fffef7 0%, #fbefce 38%, #edce8d 68%, #e3b66c 100%)',
                  color: '#101826',
                  fontSize: Math.round(120 * baseScale),
                  fontWeight: 800,
                  lineHeight: 1.02,
                  letterSpacing: 0.34,
                  textShadow: '0 1px 0 rgba(255,255,255,0.58)',
                  boxShadow:
                    `0 0 0 2px rgba(255,211,120,${(0.24 + glowBreath * 0.16).toFixed(3)}), 0 ${Math.round(18 + glowBreath * 7)}px ${Math.round(42 + glowBreath * 10)}px rgba(0,0,0,0.40), 0 5px 0 rgba(255,255,255,0.23) inset, 0 -3px 0 rgba(0,0,0,0.18) inset, 0 0 ${Math.round(46 + glowBreath * 24)}px rgba(255,214,117,${(0.20 + glowBreath * 0.18).toFixed(3)})`,
                  transform: `translateY(${Math.round(subscribeLiftY - subscribeFloatY)}px) scale(${subscribeScale})`,
                  maxWidth: '100%',
                  textAlign: 'center',
                  overflow: 'hidden'
                }}
              >
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    borderRadius: 999,
                    border: `${Math.max(1, Math.round(2 * baseScale))}px solid rgba(255,220,145,${ringOpacity.toFixed(3)})`,
                    transform: `scale(${interpolate(ringScale, [1, 1.22], [1, 1.06], {
                      extrapolateLeft: 'clamp',
                      extrapolateRight: 'clamp'
                    })})`,
                    pointerEvents: 'none',
                    zIndex: 0
                  }}
                />
                <div
                  style={{
                    position: 'absolute',
                    inset: Math.round(5 * baseScale),
                    borderRadius: 999,
                    border: '1px solid rgba(255,255,255,0.52)',
                    pointerEvents: 'none',
                    zIndex: 2
                  }}
                />
                <div
                  style={{
                    position: 'absolute',
                    inset: `-${Math.round(25 * baseScale)}% -${Math.round(18 * baseScale)}%`,
                    pointerEvents: 'none',
                    background:
                      'linear-gradient(112deg, rgba(255,255,255,0) 34%, rgba(255,255,255,0.42) 50%, rgba(255,255,255,0) 66%)',
                    transform: `translateX(${Math.round(sheenX * 85)}%) rotate(8deg)`,
                    mixBlendMode: 'screen',
                    opacity: 0.92,
                    zIndex: 1
                  }}
                />
                <span style={{position: 'relative', zIndex: 3}}>{words.cta}</span>
              </div>
            </div>

          </div>
        </div>

        <div
          style={{
            borderRadius: Math.round(26 * baseScale),
            border: '1px solid rgba(255,255,255,0.11)',
            background: 'linear-gradient(180deg, rgba(16,20,31,0.88), rgba(12,16,25,0.88))',
            padding: Math.round(14 * baseScale),
            display: 'grid',
            gridTemplateRows: '1fr',
            minWidth: 0,
            overflow: 'hidden'
          }}
        >
          <div style={{overflow: 'hidden', minHeight: 0, height: '100%'}}>
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: railGap,
                transform: `translateY(${railTranslatePct}%)`,
                willChange: 'transform'
              }}
            >
              {[0, 1].map((groupIndex) => (
                <div key={`reco-group-${groupIndex}`} style={{display: 'grid', gap: railGap, alignContent: 'start'}}>
                  {recoWithFallback.slice(0, 4).map((item, index) => {
                    const thumb = asAsset(item);
                    const title =
                      normalizeTextLine(recommendedTitles[index % Math.max(1, recommendedTitles.length)]) ||
                      `Night Prayer LoFi #${index + 1}`;

                    const delayed = Math.max(0, frame - index * 4);
                    const cardIn = spring({
                      frame: delayed,
                      fps,
                      config: {
                        damping: 200,
                        stiffness: 120,
                        mass: 0.85
                      }
                    });

                    return (
                      <div
                        key={`${groupIndex}-${item}-${index}`}
                        style={{
                          border: '1px solid rgba(255,255,255,0.11)',
                          borderRadius: Math.round(16 * baseScale),
                          padding: Math.round(10 * baseScale),
                          background: 'rgba(12,16,25,0.72)',
                          display: 'grid',
                          gridTemplateColumns: '55% 1fr',
                          gap: Math.round(8 * baseScale),
                          minWidth: 0,
                          transform: `translateY(${Math.round((1 - cardIn) * 10)}px)`,
                        }}
                      >
                        <div
                          style={{
                            aspectRatio: '16 / 9',
                            borderRadius: Math.round(10 * baseScale),
                            overflow: 'hidden',
                            background:
                              'linear-gradient(150deg, rgba(37,51,80,0.65), rgba(18,25,40,0.9))'
                          }}
                        >
                          {thumb ? (
                            <Img src={thumb} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
                          ) : (
                            <div
                              style={{
                                width: '100%',
                                height: '100%',
                                background:
                                  'radial-gradient(280px 140px at 20% 10%, rgba(116,171,255,0.28), transparent 70%), radial-gradient(220px 120px at 80% 90%, rgba(255,122,122,0.24), transparent 70%), #0c1019'
                              }}
                            />
                          )}
                        </div>
                        <div style={{display: 'grid', alignContent: 'center', gap: 0, minWidth: 0}}>
                          <div
                            style={{
                              fontSize: Math.round(34 * baseScale * cardTitleScale * 2),
                              fontWeight: 700,
                              lineHeight: 1.08,
                              overflow: 'hidden'
                            }}
                          >
                            {title}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
