import{j as r}from"./index-PEg3OjYE.js";import"./helperFunctions-BxZZh1kg.js";import"./index-CZzkuHzu.js";import"./svelte/svelte.js";const e="rgbdDecodePixelShader",t=`varying vUV: vec2f;var textureSamplerSampler: sampler;var textureSampler: texture_2d<f32>;
#include<helperFunctions>
#define CUSTOM_FRAGMENT_DEFINITIONS
@fragment
fn main(input: FragmentInputs)->FragmentOutputs {fragmentOutputs.color=vec4f(fromRGBD(textureSample(textureSampler,textureSamplerSampler,input.vUV)),1.0);}`;r.ShadersStoreWGSL[e]||(r.ShadersStoreWGSL[e]=t);const n={name:e,shader:t};export{n as rgbdDecodePixelShaderWGSL};
//# sourceMappingURL=rgbdDecode.fragment-BUgIPC_t.js.map
