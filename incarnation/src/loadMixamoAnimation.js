import * as THREE from "three";
import { FBXLoader } from "three/examples/jsm/loaders/FBXLoader.js";
import { mixamoVRMRigMap } from "./mixamoVRMRigMap.js";

export function loadMixamoAnimation(url, vrm) {
  return new Promise((resolve) => {
    const loader = new FBXLoader();

    loader.load(url, (fbx) => {
      const clip = fbx.animations[0];
      console.log("Original tracks:", clip.tracks.length);
      const tracks = [];

      clip.tracks.forEach((track) => {
        console.log("Track name:", track.name);
        const trackParts = track.name.split(".");
        const mixamoBoneName = trackParts[0];
        // const trackParts = track.name.split(".");
        // const rawName = trackParts[0];
        // const mixamoBoneName = rawName.split("|").pop();

        //const vrmBoneName = mixamoVRMRigMap[mixamoBoneName];
        const vrmBoneName = mixamoBoneName;
        console.log("Mixiamo Bone Name: ", mixamoBoneName)
        if (!vrmBoneName) return;

        // const vrmBone = vrm.humanoid.getNormalizedBoneNode(vrmBoneName);
        // console.log("VRM Bone: ", vrmBone)
        // if (!vrmBone) return;

        const newTrackName = vrmBoneName+ "." + trackParts[1];

        const convertedTrack = track.clone();
        convertedTrack.name = newTrackName;

        tracks.push(convertedTrack);
      });
      console.log("Converted tracks:", tracks.length);

      const convertedClip = new THREE.AnimationClip(
        "vrmAnimation",
        clip.duration,
        tracks
      );

      resolve(convertedClip);
    });
  });
}
