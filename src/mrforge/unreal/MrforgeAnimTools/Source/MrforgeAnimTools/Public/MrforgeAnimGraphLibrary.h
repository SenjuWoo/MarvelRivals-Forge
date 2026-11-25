#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MrforgeAnimGraphLibrary.generated.h"

class UAnimBlueprint;

/**
 * Headless AnimGraph editing for MarvelRivals-Forge (UE 5.3 Python cannot link graph pins).
 *
 * FinishPostProcessGraph turns an AnimBlueprint whose AnimGraph holds imported nodes with open ends (the
 * KawaiiPhysicsRivals JSON importer leaves the graph input and output unconnected) into a complete
 * post-process graph:  Input Pose -> imported nodes -> spring-bone jiggle nodes -> Output Pose, then compiles.
 */
UCLASS()
class MRFORGEANIMTOOLS_API UMrforgeAnimGraphLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * @param SpecJson  {"springs":[{"bone":"L_Breast_01_Jnt","stiffness":80,"damping":6,"max_displacement":3,
	 *                  "limit":true,"translate":[true,true,true],"rotate":[false,false,false]}]}
	 * @return JSON report: {"ok":bool,"nodes":n,"springs":n,"inputs_linked":n,"tail":"<node>","messages":[...]}
	 */
	UFUNCTION(BlueprintCallable, Category = "MarvelRivals-Forge")
	static FString FinishPostProcessGraph(UAnimBlueprint* AnimBlueprint, const FString& SpecJson);

	/** Pose-link wiring of the AnimGraph as JSON (node -> linked nodes), for verification. */
	UFUNCTION(BlueprintCallable, Category = "MarvelRivals-Forge")
	static FString DescribeAnimGraph(UAnimBlueprint* AnimBlueprint);
};
