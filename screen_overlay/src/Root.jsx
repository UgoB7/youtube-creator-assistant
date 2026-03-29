import {Composition} from 'remotion';
import {OverlayComposition} from './OverlayComposition';

const defaultProps = {
  width: 3840,
  height: 2160,
  fps: 30,
  durationSeconds: 12,
  assets: {
    mainVideo: 'ecran/video1.mp4',
    mainStill: 'ecran/current_video_16x9.png',
    avatar: 'ecran/channel_avatar.jpg',
    reco: ['ecran/im1.jpg', 'ecran/im2.png', 'ecran/im3.jpg', 'ecran/im4.png'],
    ytLogo: 'ecran/yt.png',
    spotifyLogo: 'ecran/spotify.png'
  },
  text: {
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
  }
};

const calculateMetadata = ({props}) => {
  const fps = Math.max(1, Number(props?.fps) || 30);
  const durationSeconds = Math.max(1, Number(props?.durationSeconds) || 12);
  const width = Math.max(1280, Number(props?.width) || 3840);
  const height = Math.max(720, Number(props?.height) || 2160);
  return {
    fps,
    width,
    height,
    durationInFrames: Math.max(1, Math.round(durationSeconds * fps))
  };
};

export const RemotionRoot = () => {
  return (
    <Composition
      id="Overlay4K"
      component={OverlayComposition}
      width={3840}
      height={2160}
      fps={30}
      durationInFrames={360}
      defaultProps={defaultProps}
      calculateMetadata={calculateMetadata}
    />
  );
};
