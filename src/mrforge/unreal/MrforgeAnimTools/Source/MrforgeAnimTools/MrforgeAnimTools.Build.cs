using UnrealBuildTool;

public class MrforgeAnimTools : ModuleRules
{
	public MrforgeAnimTools(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"UnrealEd", "BlueprintGraph", "Kismet", "KismetCompiler", "AnimGraph", "AnimGraphRuntime", "Json", "JsonUtilities"
		});
	}
}
