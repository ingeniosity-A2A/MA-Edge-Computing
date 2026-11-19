//! 24/16 evidence coupling. No weight merging, promotion, or action execution.
//! AVA-007 retains all decision and Source Truth authority.
//! 24/16 is a profile label (24 slots, 16 target dimensions), not a proven law.
use std::fmt;
pub const PROFILE_INPUT_SLOTS: usize = 24;
pub const PROFILE_STATE_DIMENSIONS: usize = 16;
#[derive(Debug,Clone,PartialEq)]
pub struct ModelContribution { pub model_id:String, pub domain:String, pub state_vector:Vec<f64>, pub confidence:f64, pub provenance:String, pub eval_score:f64, pub latency_ms:f64 }
#[derive(Debug,Clone,PartialEq)]
pub struct CouplingConstraint { pub from_domain:String, pub to_domain:String, pub max_l2_deviation:f64 }
#[derive(Debug,Clone,PartialEq)]
pub struct Disagreement { pub model_a:String, pub model_b:String, pub l2_distance:f64 }
#[derive(Debug,Clone,PartialEq)]
pub struct CoupledIntelligence { pub agreed_state:Vec<f64>, pub disagreements:Vec<Disagreement>, pub constraint_violations:Vec<String>, pub confidence:f64, pub provenance_chain:Vec<String>, pub contributor_count:usize }
#[derive(Debug,Clone,PartialEq)]
pub struct ModelMetadata { pub model_id:String, pub domain:String, pub license:String, pub plane:String, pub evaluation_status:String }
#[derive(Debug,Clone,PartialEq)]
pub enum CouplingError { EmptyContributions, EmptyIdentity, EmptyVector, DimensionMismatch, NonFiniteValue, InvalidConfidence, InvalidEvalScore, InvalidLatency, InvalidThreshold, ZeroTotalWeight }
impl fmt::Display for CouplingError { fn fmt(&self,f:&mut fmt::Formatter<'_>)->fmt::Result { write!(f,"{self:?}") } }
impl std::error::Error for CouplingError {}
pub struct IntelligenceCouplingEngine { pub constraints:Vec<CouplingConstraint>, pub disagreement_threshold:f64 }
impl Default for IntelligenceCouplingEngine {
 fn default()->Self { Self { constraints:vec![
  CouplingConstraint{from_domain:"visual_detection".into(),to_domain:"visual_classification".into(),max_l2_deviation:0.15},
  CouplingConstraint{from_domain:"retrieval".into(),to_domain:"reasoning".into(),max_l2_deviation:0.10},
  CouplingConstraint{from_domain:"evidence".into(),to_domain:"decision".into(),max_l2_deviation:0.05}], disagreement_threshold:0.3 } }
}
impl IntelligenceCouplingEngine {
 pub fn couple(&self, cs:&[ModelContribution])->Result<CoupledIntelligence,CouplingError> {
  if cs.is_empty(){return Err(CouplingError::EmptyContributions)}
  if !self.disagreement_threshold.is_finite()||self.disagreement_threshold<0.0{return Err(CouplingError::InvalidThreshold)}
  let dim=cs[0].state_vector.len(); if dim==0{return Err(CouplingError::EmptyVector)}
  for c in cs {
   if c.model_id.trim().is_empty()||c.domain.trim().is_empty()||c.provenance.trim().is_empty(){return Err(CouplingError::EmptyIdentity)}
   if c.state_vector.is_empty(){return Err(CouplingError::EmptyVector)}
   if c.state_vector.len()!=dim{return Err(CouplingError::DimensionMismatch)}
   if c.state_vector.iter().any(|v|!v.is_finite()){return Err(CouplingError::NonFiniteValue)}
   if !c.confidence.is_finite()||!(0.0..=1.0).contains(&c.confidence){return Err(CouplingError::InvalidConfidence)}
   if !c.eval_score.is_finite()||!(0.0..=1.0).contains(&c.eval_score){return Err(CouplingError::InvalidEvalScore)}
   if !c.latency_ms.is_finite()||c.latency_ms<0.0{return Err(CouplingError::InvalidLatency)}
  }
  let weights:Vec<f64>=cs.iter().map(|c|c.confidence*c.eval_score).collect();
  let total:f64=weights.iter().sum(); if !total.is_finite()||total<=0.0{return Err(CouplingError::ZeroTotalWeight)}
  let mut state=vec![0.0;dim];
  for (c,w) in cs.iter().zip(&weights){for (s,v) in state.iter_mut().zip(&c.state_vector){*s+=v*w}}
  for s in &mut state{*s/=total}
  let mut disagreements=Vec::new();
  for i in 0..cs.len(){for j in i+1..cs.len(){let d=l2(&cs[i].state_vector,&cs[j].state_vector);if d>self.disagreement_threshold{disagreements.push(Disagreement{model_a:cs[i].model_id.clone(),model_b:cs[j].model_id.clone(),l2_distance:d})}}}
  let mut violations=Vec::new();
  for rule in &self.constraints {
   if !rule.max_l2_deviation.is_finite()||rule.max_l2_deviation<0.0{return Err(CouplingError::InvalidThreshold)}
   for a in cs.iter().filter(|c|c.domain==rule.from_domain){for b in cs.iter().filter(|c|c.domain==rule.to_domain){
    let d=l2(&a.state_vector,&b.state_vector);
    if d>rule.max_l2_deviation{violations.push(format!("numeric proxy exceeded {} -> {}: L2 {:.6} > {:.6}; semantic invariant needs a domain validator",rule.from_domain,rule.to_domain,d,rule.max_l2_deviation))}
   }}
  }
  let weighted_conf=cs.iter().zip(&weights).map(|(c,w)|c.confidence*w).sum::<f64>()/total;
  let weakest=cs.iter().zip(&weights).filter(|(_,w)|**w>0.0).map(|(c,_)|c.confidence).fold(1.0_f64,f64::min);
  let provenance_chain=cs.iter().zip(&weights).map(|(c,w)|format!("{} | domain={} | source={} | eval={:.4} | confidence={:.4} | weight={:.6} | latency_ms={:.3}",c.model_id,c.domain,c.provenance,c.eval_score,c.confidence,w,c.latency_ms)).collect();
  Ok(CoupledIntelligence{agreed_state:state,disagreements,constraint_violations:violations,confidence:weighted_conf.min(weakest),provenance_chain,contributor_count:cs.len()})
 }
}
fn l2(a:&[f64],b:&[f64])->f64{a.iter().zip(b).map(|(x,y)|(x-y).powi(2)).sum::<f64>().sqrt()}
/// Candidate catalogue only. Registration is not approval, execution, or promotion.
pub fn candidate_registry()->Vec<ModelMetadata>{vec![
 ModelMetadata{model_id:"LiquidAI/LFM3-Omni-2B".into(),domain:"omni_perception".into(),license:"LFM Open License v1.0; review required".into(),plane:"device_candidate".into(),evaluation_status:"untested".into()},
 ModelMetadata{model_id:"nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-GGUF".into(),domain:"local_reasoning".into(),license:"NVIDIA terms; review required".into(),plane:"device_candidate".into(),evaluation_status:"untested".into()},
 ModelMetadata{model_id:"nvidia/Nemotron-Labs-Audex-2B".into(),domain:"audio_specialist".into(),license:"One-Way Noncommercial; commercial use blocked pending permission".into(),plane:"research_only".into(),evaluation_status:"untested".into()},
 ModelMetadata{model_id:"JetBrains/Mellum2.1-12B-A2.5B-Thinking-GGUF".into(),domain:"coding_technical".into(),license:"JetBrains terms; review required".into(),plane:"remote_candidate".into(),evaluation_status:"untested".into()},
 ModelMetadata{model_id:"vectionlabs/Salience-27B-R6".into(),domain:"remote_specialist".into(),license:"Apache-2.0 claim; verify artifact metadata".into(),plane:"remote_candidate".into(),evaluation_status:"untested".into()},
 ModelMetadata{model_id:"d3-ultra (26.09B multimodal decision)".into(),domain:"remote_visual_decision".into(),license:"Apache-2.0 claim; verify source artifact".into(),plane:"external_compute_candidate".into(),evaluation_status:"untested".into()},
 ModelMetadata{model_id:"Drex Max v1.1".into(),domain:"decision_service".into(),license:"Vendor API terms; review required".into(),plane:"remote_api_candidate".into(),evaluation_status:"untested".into()}]}
#[cfg(test)] mod tests{
 use super::*; fn c(id:&str,domain:&str,v:Vec<f64>,e:f64,q:f64)->ModelContribution{ModelContribution{model_id:id.into(),domain:domain.into(),state_vector:v,confidence:q,provenance:"test:fixture@sha256:known".into(),eval_score:e,latency_ms:1.0}}
 #[test]fn weighted_consensus(){let r=IntelligenceCouplingEngine::default().couple(&[c("a","x",vec![1.0,2.0],1.0,1.0),c("b","x",vec![3.0,4.0],1.0,1.0)]).unwrap();assert_eq!(r.agreed_state,vec![2.0,3.0]);}
 #[test]fn detects_disagreement(){let r=IntelligenceCouplingEngine::default().couple(&[c("a","x",vec![0.0],1.0,1.0),c("b","y",vec![1.0],1.0,1.0)]).unwrap();assert_eq!(r.disagreements.len(),1);}
 #[test]fn rejects_dimension_mismatch(){assert_eq!(IntelligenceCouplingEngine::default().couple(&[c("a","x",vec![1.0],1.0,1.0),c("b","y",vec![1.0,2.0],1.0,1.0)]),Err(CouplingError::DimensionMismatch));}
 #[test]fn rejects_zero_weight(){assert_eq!(IntelligenceCouplingEngine::default().couple(&[c("a","x",vec![1.0],0.0,0.9)]),Err(CouplingError::ZeroTotalWeight));}
 #[test]fn rejects_nonfinite_and_bad_confidence(){assert_eq!(IntelligenceCouplingEngine::default().couple(&[c("a","x",vec![f64::NAN],1.0,1.0)]),Err(CouplingError::NonFiniteValue));assert_eq!(IntelligenceCouplingEngine::default().couple(&[c("a","x",vec![1.0],1.0,1.1)]),Err(CouplingError::InvalidConfidence));}
 #[test]fn registry_has_no_scores(){let m=candidate_registry();assert_eq!(m.len(),7);assert!(m.iter().all(|x|x.evaluation_status=="untested"));}
}